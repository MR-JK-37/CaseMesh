import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, any_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import (
    CASE_STATUSES,
    MATTER_TYPES,
    Case,
    CaseEvent,
    CaseInstitutionLink,
    CaseTransfer,
    Institution,
)
from app.services.alerts import raise_alert
from app.services.audit import append_audit_entry
from app.services.cases import compute_projection_updates, format_case_number
from app.services.overlap import recompute_overlap_for_institution
from app.services.realtime import publish
from app.services.sla import fetch_holidays, fetch_policy, sla_facts_for_case

router = APIRouter(prefix="/cases", tags=["cases"])

SOURCE_CHANNELS = ("letter", "email", "cpgrams", "walk_in", "phone", "other")
PRIORITIES = ("standard", "priority")


def _json_safe(value):
    """`CaseEvent.payload` is JSONB — datetimes/dates/UUIDs aren't
    directly JSON-serializable, but `compute_projection_updates` (the
    one place that interprets payloads, shared with
    scripts/rebuild_projection.py) needs the typed Python values back
    out of `payload` symmetrically, so this only transforms the stored
    copy, never what's passed to that function."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (uuid.UUID, dt.date, dt.datetime)):
        return str(value)
    return value


async def _append_event(
    session: AsyncSession,
    case: Case,
    *,
    event_type: str,
    principal: Principal,
    payload: dict,
    remark: str | None = None,
) -> CaseEvent:
    """Section 6.3: one transaction, event + projection + audit. The
    caller's `session` (from `get_scoped_session`) is already inside a
    transaction (`core/db.py`'s `get_tenant_session`) — this never calls
    commit() itself, so every endpoint using it keeps its own atomicity."""
    # Explicitly set (not the column's server_default) and reused below
    # for the projection update: using two different clocks — Python's
    # for the projection, Postgres's own now() for the stored event —
    # meant live `disposed_at`/`last_action_at` could never exactly
    # equal what scripts/rebuild_projection.py replays from the
    # persisted event, a real (if small) drift this test caught.
    now = dt.datetime.now(dt.UTC)
    event = CaseEvent(
        case_id=case.id,
        event_type=event_type,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        payload=_json_safe(payload),
        remark=remark,
        created_at=now,
    )
    session.add(event)

    outcome = compute_projection_updates(case.status, event_type, payload, now)
    for field_name, value in outcome.fields.items():
        setattr(case, field_name, value)

    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action=f"case_{event_type}",
        resource_type="case",
        resource_id=str(case.id),
    )
    await session.flush()

    # Section 8.4's event-driven trigger: every event is a reason to
    # recheck this case's institution(s) for new overlaps, not just a
    # fixed "significant action" list — Phase 3's event vocabulary has
    # no show-cause/inspection/penalty granularity to filter on, so this
    # phase recomputes on every event type (see
    # app/services/overlap.py's docstring and docs/decision-log.md).
    inst_ids = (
        await session.execute(select(CaseInstitutionLink.institution_id).where(CaseInstitutionLink.case_id == case.id))
    ).scalars().all()
    for inst_id in inst_ids:
        await recompute_overlap_for_institution(session, inst_id, actor_role=principal.role)

    # Section 6.4: every case event is real-time-worthy T1 data (case
    # ID, status, actor role — never the remark itself) for the
    # handling bureau's officers and anyone subscribed to this case.
    realtime_payload = {
        "case_id": str(case.id),
        "case_number": case.case_number,
        "event_type": event_type,
        "status": case.status,
    }
    if case.assigned_bureau_id:
        await publish(session, channel=f"bureau:{case.assigned_bureau_id}", event_type="case_updated", payload=realtime_payload)
    await publish(session, channel=f"case:{case.id}", event_type="case_updated", payload=realtime_payload)

    if event_type == "escalated":
        # Section 7.3: ESCALATION_RAISED — each escalation action is its
        # own threshold crossing, so dedup is per *event*, not per case
        # (a case can be escalated, resolved, and escalated again later).
        channels = [f"bureau:{case.assigned_bureau_id}"] if case.assigned_bureau_id else []
        await raise_alert(
            session,
            code="ESCALATION_RAISED",
            severity="warning",
            resource_type="case",
            resource_id=case.id,
            message=f"Case {case.case_number} was escalated.",
            dedup_key=f"ESCALATION_RAISED:{event.id}",
            channels=[*channels, "broadcast:all"],
        )

    return event


async def _get_case_or_404(session: AsyncSession, case_id: str) -> Case:
    case = (await session.execute(select(Case).where(Case.id == uuid.UUID(case_id)))).scalar_one_or_none()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


def _require_handling_bureau(principal: Principal, case: Case, action: str) -> None:
    """OWN_BUREAU scope checked against the case's *current* handling
    bureau — `can()` only validates the role/scope shape, the actual
    bureau match happens here where the resource is known."""
    resource_bureau_ids = frozenset({str(case.assigned_bureau_id)}) if case.assigned_bureau_id else frozenset()
    if not can(principal.role, action, actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this case's handling bureau")


# --- Schemas ---------------------------------------------------------


class CaseOut(BaseModel):
    id: str
    case_number: str
    matter_type: str
    source_channel: str
    priority: str
    confidential: bool
    status: str
    received_at: str
    expected_disposal_date: str | None
    disposed_at: str | None
    disposal_type: str | None
    assigned_bureau_id: str | None
    assigned_officer_id: str | None
    last_action_type: str
    last_action_at: str
    next_action_required: str | None
    institution_ids: list[str]
    due_at: str | None
    sla_status: str


async def _to_out(
    session: AsyncSession,
    case: Case,
    institution_ids: list[uuid.UUID],
    *,
    holidays: frozenset[dt.date] | None = None,
) -> CaseOut:
    sla = await sla_facts_for_case(
        session,
        source_channel=case.source_channel,
        matter_type=case.matter_type,
        priority=case.priority,
        received_at=case.received_at,
        holidays=holidays,
    )
    return CaseOut(
        id=str(case.id),
        case_number=case.case_number,
        matter_type=case.matter_type,
        source_channel=case.source_channel,
        priority=case.priority,
        confidential=case.confidential,
        status=case.status,
        received_at=case.received_at.isoformat(),
        expected_disposal_date=case.expected_disposal_date.isoformat() if case.expected_disposal_date else None,
        disposed_at=case.disposed_at.isoformat() if case.disposed_at else None,
        disposal_type=case.disposal_type,
        assigned_bureau_id=str(case.assigned_bureau_id) if case.assigned_bureau_id else None,
        assigned_officer_id=str(case.assigned_officer_id) if case.assigned_officer_id else None,
        last_action_type=case.last_action_type,
        last_action_at=case.last_action_at.isoformat(),
        next_action_required=case.next_action_required,
        institution_ids=[str(i) for i in institution_ids],
        due_at=sla.due_at.isoformat() if sla.due_at else None,
        sla_status=sla.status,
    )


async def _institution_ids_for(session: AsyncSession, case_id: uuid.UUID) -> list[uuid.UUID]:
    return (
        await session.execute(
            select(CaseInstitutionLink.institution_id).where(CaseInstitutionLink.case_id == case_id)
        )
    ).scalars().all()


# --- Duplicate pre-check ----------------------------------------------


class DuplicateCandidateOut(BaseModel):
    id: str
    case_number: str
    status: str
    assigned_bureau_id: str | None
    matter_type: str


@router.get("/duplicate-check", response_model=list[DuplicateCandidateOut])
async def duplicate_check(
    institution_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 5/R3: "shows likely matches before the officer submits" —
    every open (non-disposed) case already registered against this
    institution, regardless of which bureau holds it. Advisory only:
    the caller decides whether to proceed (Section 8's full overlap
    engine with text-similarity scoring is Phase 4; this is the
    same-institution hard match Section 8.3 calls INFO-level).

    This is a pre-submission check, not scoped to a specific resource
    bureau yet — for an OWN_BUREAU-scoped role it's "can I register at
    all for my own bureau", so resource_bureau_ids is the actor's own
    bureau_ids (self-scope). Omitting this makes the OWN_BUREAU
    intersection always empty, 403-ing bureau_head/case_officer on every
    registration attempt — found live via the case-registration screen's
    duplicate-check call."""
    if not can(
        principal.role,
        "case:register",
        actor_bureau_ids=principal.bureau_ids,
        resource_bureau_ids=principal.bureau_ids,
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (
        await session.execute(
            select(Case)
            .join(CaseInstitutionLink, CaseInstitutionLink.case_id == Case.id)
            .where(CaseInstitutionLink.institution_id == uuid.UUID(institution_id))
            .where(Case.status != "disposed")
        )
    ).scalars().all()
    return [
        DuplicateCandidateOut(
            id=str(c.id),
            case_number=c.case_number,
            status=c.status,
            assigned_bureau_id=str(c.assigned_bureau_id) if c.assigned_bureau_id else None,
            matter_type=c.matter_type,
        )
        for c in rows
    ]


# --- Register -----------------------------------------------------------


class RegisterCaseRequest(BaseModel):
    institution_ids: list[str]
    matter_type: str
    source_channel: str
    priority: str = "standard"
    confidential: bool = False
    received_at: str | None = None
    assigned_bureau_id: str
    assigned_officer_id: str | None = None
    expected_disposal_date: str | None = None
    next_action_required: str | None = None
    external_refs: list[str] = []
    description: str | None = None


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def register_case(
    body: RegisterCaseRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 5/R3: every mandatory field is required by the schema
    itself (FastAPI 422s on a missing one) — case ID, date of receipt,
    nature/category, assigned Bureau/Cell are all set here; status,
    last action, and expected disposal date are set by the projection
    update, not hand-assigned (Section 6.3)."""
    if not can(
        principal.role,
        "case:register",
        actor_bureau_ids=principal.bureau_ids,
        resource_bureau_ids=frozenset({body.assigned_bureau_id}),
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    if body.matter_type not in MATTER_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown matter_type: {body.matter_type}")
    if body.source_channel not in SOURCE_CHANNELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown source_channel: {body.source_channel}")
    if body.priority not in PRIORITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown priority: {body.priority}")
    if not body.institution_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one institution is required")

    existing_institutions = (
        await session.execute(select(Institution.id).where(Institution.id.in_([uuid.UUID(i) for i in body.institution_ids])))
    ).scalars().all()
    if len(existing_institutions) != len(body.institution_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more institution_ids do not exist")

    received_at = dt.datetime.fromisoformat(body.received_at) if body.received_at else dt.datetime.now(dt.UTC)

    seq_value = (await session.execute(select(func.nextval("cases_seq_seq")))).scalar_one()
    case = Case(
        seq=seq_value,
        case_number=format_case_number(seq_value, received_at.year),
        status="pending",
        matter_type=body.matter_type,
        source_channel=body.source_channel,
        priority=body.priority,
        confidential=body.confidential,
        external_refs=body.external_refs,
        received_at=received_at,
        last_action_type="registered",
        registered_by=uuid.UUID(principal.user_id),
    )
    session.add(case)
    await session.flush()

    for inst_id in body.institution_ids:
        session.add(CaseInstitutionLink(case_id=case.id, institution_id=uuid.UUID(inst_id)))

    await _append_event(
        session,
        case,
        event_type="registered",
        principal=principal,
        payload={
            "matter_type": body.matter_type,
            "source_channel": body.source_channel,
            "priority": body.priority,
            "confidential": body.confidential,
            "received_at": received_at,
            "assigned_bureau_id": uuid.UUID(body.assigned_bureau_id),
            "assigned_officer_id": uuid.UUID(body.assigned_officer_id) if body.assigned_officer_id else None,
            "expected_disposal_date": dt.date.fromisoformat(body.expected_disposal_date) if body.expected_disposal_date else None,
            "next_action_required": body.next_action_required,
            # T2 content only (Section 4.3) — never projected onto
            # `cases` itself (see Case's docstring). Optional: R3's
            # mandatory-field list doesn't require a free-text
            # description, but Section 8.3's text-similarity overlap
            # signal needs *something* to compare, and officers
            # typically have a line or two to give even for a
            # letter/walk-in intake.
            "description": body.description,
        },
    )
    await session.flush()

    # Section 7.2: "For every other combination the policy is absent:
    # the case shows 'SLA policy not set, contact admin' ... and a
    # SLA_POLICY_MISSING alert goes to super_admin and the bureau
    # head." Deduped per policy *gap* (source+matter_type+priority),
    # not per case — the gap is systemic, not case-specific, so one
    # alert per gap is correct even as more cases hit the same gap.
    policy = await fetch_policy(
        session, source_channel=body.source_channel, matter_type=body.matter_type, priority=body.priority
    )
    if policy is None:
        await raise_alert(
            session,
            code="SLA_POLICY_MISSING",
            severity="warning",
            resource_type="sla_gap",
            resource_id=None,
            message=(
                f"No SLA policy for source={body.source_channel}, "
                f"matter_type={body.matter_type}, priority={body.priority}."
            ),
            dedup_key=f"SLA_POLICY_MISSING:{body.source_channel}:{body.matter_type}:{body.priority}",
            channels=[f"bureau:{body.assigned_bureau_id}", "broadcast:all"],
        )
    return await _to_out(session, case, [uuid.UUID(i) for i in body.institution_ids])


# --- List / detail -------------------------------------------------------


class CaseListOut(BaseModel):
    items: list[CaseOut]
    next_cursor: str | None


@router.get("", response_model=CaseListOut)
async def list_cases(
    q: str | None = Query(None, description="Matches case number, external refs, or institution name/Permanent ID"),
    status_filter: str | None = Query(None, alias="status"),
    matter_type: str | None = None,
    priority: str | None = None,
    source_channel: str | None = None,
    bureau_id: str | None = None,
    region_id: str | None = None,
    institution_id: str | None = None,
    received_from: str | None = None,
    received_to: str | None = None,
    cursor: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 4.3 T1: coordination metadata, broadly visible to every
    authenticated official — this is exactly what lets RB see PGRC is
    handling the same institution (Section 5's core ask), without
    exposing case content (that's `/cases/{id}/events`, Section 4.3
    T2, bureau-restricted).

    Section 9.7/R9's search/filter + Section 10's "keyset pagination
    everywhere" — the previous build this is replacing returned
    unbounded lists; this one caps at `limit` (default 50, max 200)
    and returns `next_cursor` (the last row's `seq`) for the caller to
    pass back, rather than an offset that drifts under concurrent
    writes."""
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    stmt = select(Case)
    conditions = []
    if status_filter:
        conditions.append(Case.status == status_filter)
    if matter_type:
        conditions.append(Case.matter_type == matter_type)
    if priority:
        conditions.append(Case.priority == priority)
    if source_channel:
        conditions.append(Case.source_channel == source_channel)
    if bureau_id:
        conditions.append(Case.assigned_bureau_id == uuid.UUID(bureau_id))
    if received_from:
        conditions.append(Case.received_at >= dt.datetime.fromisoformat(received_from))
    if received_to:
        conditions.append(Case.received_at <= dt.datetime.fromisoformat(received_to))
    if cursor is not None:
        conditions.append(Case.seq < cursor)

    if institution_id or region_id or q:
        stmt = stmt.join(CaseInstitutionLink, CaseInstitutionLink.case_id == Case.id)
        stmt = stmt.join(Institution, Institution.id == CaseInstitutionLink.institution_id)
        if institution_id:
            conditions.append(CaseInstitutionLink.institution_id == uuid.UUID(institution_id))
        if region_id:
            conditions.append(Institution.region_id == uuid.UUID(region_id))
        if q:
            like = f"%{q}%"
            conditions.append(
                or_(
                    Case.case_number.ilike(like),
                    q == any_(Case.external_refs),
                    Institution.name.ilike(like),
                    Institution.permanent_id.ilike(like),
                )
            )

    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(Case.seq.desc()).distinct().limit(limit)

    rows = (await session.execute(stmt)).scalars().unique().all()
    holidays = await fetch_holidays(session)
    out = []
    for c in rows:
        inst_ids = await _institution_ids_for(session, c.id)
        out.append(await _to_out(session, c, inst_ids, holidays=holidays))
    next_cursor = str(rows[-1].seq) if len(rows) == limit else None
    return CaseListOut(items=out, next_cursor=next_cursor)


@router.get("/counters")
async def case_counters(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 6.5: computed directly from raw rows every time (no
    cached `dashboard_counters` yet — Phase 6) specifically so
    tests/test_case_counters.py's reconciliation check has something
    real to compare against: this function *is* the reconciliation
    query."""
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (await session.execute(select(Case.status, func.count()).group_by(Case.status))).all()
    counts = {status_name: 0 for status_name in CASE_STATUSES}
    for status_name, count in rows:
        counts[status_name] = count
    counts["total"] = sum(counts.values())
    return counts


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(
    case_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    case = await _get_case_or_404(session, case_id)
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


class CaseEventOut(BaseModel):
    id: str
    event_type: str
    actor_role: str
    remark: str | None
    payload: dict
    created_at: str


@router.get("/{case_id}/events", response_model=list[CaseEventOut])
async def get_case_events(
    case_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 4.3 T2 / R8: the real content boundary. Only the handling
    bureau and `competent_authority` see the timeline; everyone else
    gets a 403, not a redacted version — Postgres RLS on `case_events`
    (Phase 3 migration) independently enforces the same boundary even
    if this check is ever bypassed."""
    case = await _get_case_or_404(session, case_id)
    _require_handling_bureau(principal, case, "case:read_events")
    rows = (
        await session.execute(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.seq))
    ).scalars().all()
    return [
        CaseEventOut(
            id=str(e.id),
            event_type=e.event_type,
            actor_role=e.actor_role,
            remark=e.remark,
            payload={k: str(v) for k, v in e.payload.items()},
            created_at=e.created_at.isoformat(),
        )
        for e in rows
    ]


# --- Workflow actions ------------------------------------------------


class AssignRequest(BaseModel):
    officer_id: str


@router.post("/{case_id}/assign", response_model=CaseOut, dependencies=[Depends(require_csrf)])
async def assign_case(
    case_id: str,
    body: AssignRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    _require_handling_bureau(principal, case, "case:assign")
    event_type = "reassigned" if case.assigned_officer_id else "assigned"
    await _append_event(
        session, case, event_type=event_type, principal=principal, payload={"officer_id": uuid.UUID(body.officer_id)}
    )
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


class RemarkRequest(BaseModel):
    remark: str
    next_action_required: str | None = None
    expected_disposal_date: str | None = None


@router.post("/{case_id}/remark", response_model=CaseOut, dependencies=[Depends(require_csrf)])
async def add_remark(
    case_id: str,
    body: RemarkRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    _require_handling_bureau(principal, case, "case:remark")
    payload: dict = {}
    if body.next_action_required is not None:
        payload["next_action_required"] = body.next_action_required
    if body.expected_disposal_date is not None:
        payload["expected_disposal_date"] = dt.date.fromisoformat(body.expected_disposal_date)
    await _append_event(session, case, event_type="remark_added", principal=principal, payload=payload, remark=body.remark)
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


class TransferOut(BaseModel):
    id: str
    from_bureau_id: str
    to_bureau_id: str
    state: str
    reason: str | None
    proposed_at: str


@router.get("/{case_id}/transfers", response_model=list[TransferOut])
async def list_transfers(
    case_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """T1: transfer state (not the reason/remark free text) is
    coordination metadata, same visibility as the rest of `cases` — a
    bureau needs to see an incoming proposal exists in order to act on
    it, which is exactly Section 9.6's "transfers awaiting acceptance"
    tile."""
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (
        await session.execute(
            select(CaseTransfer).where(CaseTransfer.case_id == uuid.UUID(case_id)).order_by(CaseTransfer.proposed_at.desc())
        )
    ).scalars().all()
    return [
        TransferOut(
            id=str(t.id),
            from_bureau_id=str(t.from_bureau_id),
            to_bureau_id=str(t.to_bureau_id),
            state=t.state,
            reason=t.reason,
            proposed_at=t.proposed_at.isoformat(),
        )
        for t in rows
    ]


class TransferProposeRequest(BaseModel):
    to_bureau_id: str
    reason: str


@router.post("/{case_id}/transfer/propose", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def propose_transfer(
    case_id: str,
    body: TransferProposeRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    _require_handling_bureau(principal, case, "case:transfer_propose")
    if not case.assigned_bureau_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Case has no current bureau to transfer from")

    transfer = CaseTransfer(
        case_id=case.id,
        from_bureau_id=case.assigned_bureau_id,
        to_bureau_id=uuid.UUID(body.to_bureau_id),
        state="proposed",
        reason=body.reason,
        proposed_by=uuid.UUID(principal.user_id),
    )
    session.add(transfer)
    await _append_event(
        session,
        case,
        event_type="transfer_proposed",
        principal=principal,
        payload={"to_bureau_id": body.to_bureau_id, "reason": body.reason},
        remark=body.reason,
    )
    await session.flush()
    return {"transfer_id": str(transfer.id)}


@router.post(
    "/{case_id}/transfer/{transfer_id}/accept", response_model=CaseOut, dependencies=[Depends(require_csrf)]
)
async def accept_transfer(
    case_id: str,
    transfer_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    transfer = (
        await session.execute(select(CaseTransfer).where(CaseTransfer.id == uuid.UUID(transfer_id)))
    ).scalar_one_or_none()
    if transfer is None or str(transfer.case_id) != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    if transfer.state != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Transfer already resolved")

    resource_bureau_ids = frozenset({str(transfer.to_bureau_id)})
    if not can(principal.role, "case:transfer_resolve", actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the receiving bureau can accept this transfer")

    transfer.state = "accepted"
    transfer.resolved_by = uuid.UUID(principal.user_id)
    transfer.resolved_at = dt.datetime.now(dt.UTC)
    await _append_event(
        session, case, event_type="transfer_accepted", principal=principal, payload={"to_bureau_id": str(transfer.to_bureau_id)}
    )
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


@router.post(
    "/{case_id}/transfer/{transfer_id}/reject", response_model=CaseOut, dependencies=[Depends(require_csrf)]
)
async def reject_transfer(
    case_id: str,
    transfer_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    transfer = (
        await session.execute(select(CaseTransfer).where(CaseTransfer.id == uuid.UUID(transfer_id)))
    ).scalar_one_or_none()
    if transfer is None or str(transfer.case_id) != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    if transfer.state != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Transfer already resolved")

    resource_bureau_ids = frozenset({str(transfer.to_bureau_id)})
    if not can(principal.role, "case:transfer_resolve", actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the receiving bureau can reject this transfer")

    transfer.state = "rejected"
    transfer.resolved_by = uuid.UUID(principal.user_id)
    transfer.resolved_at = dt.datetime.now(dt.UTC)
    await _append_event(session, case, event_type="transfer_rejected", principal=principal, payload={})
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


@router.post("/{case_id}/escalate", response_model=CaseOut, dependencies=[Depends(require_csrf)])
async def escalate_case(
    case_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    _require_handling_bureau(principal, case, "case:escalate")
    await _append_event(session, case, event_type="escalated", principal=principal, payload={})
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


class DisposeRequest(BaseModel):
    disposal_type: str
    remark: str


@router.post("/{case_id}/dispose", response_model=CaseOut, dependencies=[Depends(require_csrf)])
async def dispose_case(
    case_id: str,
    body: DisposeRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    _require_handling_bureau(principal, case, "case:dispose")
    await _append_event(
        session,
        case,
        event_type="disposed",
        principal=principal,
        payload={"disposal_type": body.disposal_type},
        remark=body.remark,
    )
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)


@router.post("/{case_id}/reopen", response_model=CaseOut, dependencies=[Depends(require_csrf)])
async def reopen_case(
    case_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    case = await _get_case_or_404(session, case_id)
    if case.status != "disposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a disposed case can be reopened")
    # competent_authority has Scope.ALL for this action; bureau_head has
    # Scope.OWN_BUREAU — either is sufficient.
    resource_bureau_ids = frozenset({str(case.assigned_bureau_id)}) if case.assigned_bureau_id else frozenset()
    if not can(
        principal.role, "case:reopen", actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    await _append_event(session, case, event_type="reopened", principal=principal, payload={})
    inst_ids = await _institution_ids_for(session, case.id)
    return await _to_out(session, case, inst_ids)
