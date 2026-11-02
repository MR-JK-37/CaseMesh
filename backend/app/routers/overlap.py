import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import (
    COORDINATION_DECISION_TYPES,
    Case,
    CoordinationDecision,
    CoordinationMessage,
    CoordinationThread,
    Institution,
    OverlapCandidate,
    OverlapGroup,
)
from app.services.audit import append_audit_entry

router = APIRouter(tags=["overlap"])

_LEVEL_RANK = {"info": 0, "potential": 1, "high": 2}


def _require_overlap_access(principal: Principal, case_a: Case, case_b: Case, action: str) -> None:
    """Section 8.5's officer actions (confirm/dismiss/coordinate/decide)
    are scoped to either member case's handling bureau — mirrors
    `app/routers/cases.py`'s `_require_handling_bureau`, but the
    resource here is a *pair*, so the union of both cases' bureaus is
    what an OWN_BUREAU-scoped role is checked against."""
    resource_bureau_ids = frozenset(
        str(b) for b in (case_a.assigned_bureau_id, case_b.assigned_bureau_id) if b
    )
    if not can(principal.role, action, actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this pair's handling bureau(s)")


async def _get_cases(session: AsyncSession, case_a_id: uuid.UUID, case_b_id: uuid.UUID) -> tuple[Case, Case]:
    case_a = (await session.execute(select(Case).where(Case.id == case_a_id))).scalar_one()
    case_b = (await session.execute(select(Case).where(Case.id == case_b_id))).scalar_one()
    return case_a, case_b


async def _get_candidate_or_404(session: AsyncSession, candidate_id: str) -> OverlapCandidate:
    row = (
        await session.execute(select(OverlapCandidate).where(OverlapCandidate.id == uuid.UUID(candidate_id)))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Overlap candidate not found")
    return row


# --- Schemas -----------------------------------------------------------


class OverlapReasonOut(BaseModel):
    code: str
    text: str


class OverlapCandidateOut(BaseModel):
    id: str
    group_id: str
    institution_id: str
    case_a_id: str
    case_a_number: str
    case_a_bureau_id: str | None
    case_b_id: str
    case_b_number: str
    case_b_bureau_id: str | None
    score: int
    level: str
    reasons: list[OverlapReasonOut]
    config_version: str
    computed_at: str
    status: str
    relationship_type: str | None
    dismiss_reason: str | None
    thread_id: str | None


async def _candidate_out(session: AsyncSession, row: OverlapCandidate, institution_id: uuid.UUID) -> OverlapCandidateOut:
    case_a, case_b = await _get_cases(session, row.case_a_id, row.case_b_id)
    thread_id = (
        await session.execute(select(CoordinationThread.id).where(CoordinationThread.candidate_id == row.id))
    ).scalar_one_or_none()
    return OverlapCandidateOut(
        id=str(row.id),
        group_id=str(row.group_id),
        institution_id=str(institution_id),
        case_a_id=str(case_a.id),
        case_a_number=case_a.case_number,
        case_a_bureau_id=str(case_a.assigned_bureau_id) if case_a.assigned_bureau_id else None,
        case_b_id=str(case_b.id),
        case_b_number=case_b.case_number,
        case_b_bureau_id=str(case_b.assigned_bureau_id) if case_b.assigned_bureau_id else None,
        score=row.score,
        level=row.level,
        reasons=[OverlapReasonOut(**r) for r in row.reasons],
        config_version=row.config_version,
        computed_at=row.computed_at.isoformat(),
        status=row.status,
        relationship_type=row.relationship_type,
        dismiss_reason=row.dismiss_reason,
        thread_id=str(thread_id) if thread_id else None,
    )


class OverlapGroupOut(BaseModel):
    id: str
    institution_id: str
    institution_name: str
    max_level: str
    candidates: list[OverlapCandidateOut]
    updated_at: str


async def _group_out(session: AsyncSession, group: OverlapGroup) -> OverlapGroupOut:
    institution = (
        await session.execute(select(Institution).where(Institution.id == group.institution_id))
    ).scalar_one()
    rows = (
        await session.execute(select(OverlapCandidate).where(OverlapCandidate.group_id == group.id))
    ).scalars().all()
    candidates = [await _candidate_out(session, r, group.institution_id) for r in rows]
    max_level = "info"
    for c in candidates:
        if _LEVEL_RANK[c.level] > _LEVEL_RANK[max_level]:
            max_level = c.level
    return OverlapGroupOut(
        id=str(group.id),
        institution_id=str(group.institution_id),
        institution_name=institution.name,
        max_level=max_level,
        candidates=candidates,
        updated_at=group.updated_at.isoformat(),
    )


# --- Queue (Section 8.5: "Group by institution... one overlap_group
# per institution") ------------------------------------------------------


@router.get("/overlap/groups", response_model=list[OverlapGroupOut])
async def list_overlap_groups(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "overlap:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (
        await session.execute(select(OverlapGroup).where(OverlapGroup.id.in_(select(OverlapCandidate.group_id))))
    ).scalars().all()
    groups = [await _group_out(session, g) for g in rows]
    groups.sort(key=lambda g: _LEVEL_RANK[g.max_level], reverse=True)
    return groups


@router.get("/institutions/{institution_id}/overlap-group", response_model=OverlapGroupOut | None)
async def get_overlap_group_for_institution(
    institution_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Backs the institution-profile banner (Section 8.5)."""
    if not can(principal.role, "overlap:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    group = (
        await session.execute(select(OverlapGroup).where(OverlapGroup.institution_id == uuid.UUID(institution_id)))
    ).scalar_one_or_none()
    if group is None:
        return None
    return await _group_out(session, group)


@router.get("/cases/{case_id}/overlaps", response_model=list[OverlapCandidateOut])
async def get_overlaps_for_case(
    case_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Backs the case-detail banner (Section 8.5)."""
    if not can(principal.role, "overlap:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    cid = uuid.UUID(case_id)
    rows = (
        await session.execute(
            select(OverlapCandidate).where((OverlapCandidate.case_a_id == cid) | (OverlapCandidate.case_b_id == cid))
        )
    ).scalars().all()
    out = []
    for r in rows:
        group = (await session.execute(select(OverlapGroup).where(OverlapGroup.id == r.group_id))).scalar_one()
        out.append(await _candidate_out(session, r, group.institution_id))
    return out


# --- Officer actions on a candidate pair --------------------------------


class ConfirmRequest(BaseModel):
    relationship_type: str


@router.post("/overlap/candidates/{candidate_id}/confirm", response_model=OverlapCandidateOut, dependencies=[Depends(require_csrf)])
async def confirm_candidate(
    candidate_id: str,
    body: ConfirmRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 8.5: "Confirm and link (choose relationship)"."""
    row = await _get_candidate_or_404(session, candidate_id)
    case_a, case_b = await _get_cases(session, row.case_a_id, row.case_b_id)
    _require_overlap_access(principal, case_a, case_b, "overlap:confirm")
    row.status = "confirmed"
    row.relationship_type = body.relationship_type
    row.dismiss_reason = None
    row.decided_by = uuid.UUID(principal.user_id)
    row.decided_at = dt.datetime.now(dt.UTC)
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="overlap_confirmed",
        resource_type="overlap_candidate",
        resource_id=str(row.id),
    )
    await session.flush()
    group = (await session.execute(select(OverlapGroup).where(OverlapGroup.id == row.group_id))).scalar_one()
    return await _candidate_out(session, row, group.institution_id)


class DismissRequest(BaseModel):
    reason: str


@router.post("/overlap/candidates/{candidate_id}/dismiss", response_model=OverlapCandidateOut, dependencies=[Depends(require_csrf)])
async def dismiss_candidate(
    candidate_id: str,
    body: DismissRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 8.5: "Dismiss (reason required, feeds tuning)" — the
    reason is what `scripts/eval_overlap.py` reads as a negative label."""
    if not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A dismiss reason is required")
    row = await _get_candidate_or_404(session, candidate_id)
    case_a, case_b = await _get_cases(session, row.case_a_id, row.case_b_id)
    _require_overlap_access(principal, case_a, case_b, "overlap:dismiss")
    row.status = "dismissed"
    row.dismiss_reason = body.reason
    row.relationship_type = None
    row.decided_by = uuid.UUID(principal.user_id)
    row.decided_at = dt.datetime.now(dt.UTC)
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="overlap_dismissed",
        resource_type="overlap_candidate",
        resource_id=str(row.id),
    )
    await session.flush()
    group = (await session.execute(select(OverlapGroup).where(OverlapGroup.id == row.group_id))).scalar_one()
    return await _candidate_out(session, row, group.institution_id)


# --- Coordination threads -----------------------------------------------


class ThreadOut(BaseModel):
    id: str
    candidate_id: str
    lead_bureau_id: str | None
    status: str
    created_at: str


class StartCoordinationRequest(BaseModel):
    lead_bureau_id: str | None = None


@router.post(
    "/overlap/candidates/{candidate_id}/coordinate",
    response_model=ThreadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def start_coordination(
    candidate_id: str,
    body: StartCoordinationRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 8.5: "Start coordination (thread, optional lead bureau...)"."""
    row = await _get_candidate_or_404(session, candidate_id)
    case_a, case_b = await _get_cases(session, row.case_a_id, row.case_b_id)
    _require_overlap_access(principal, case_a, case_b, "overlap:coordinate")

    existing = (
        await session.execute(select(CoordinationThread).where(CoordinationThread.candidate_id == row.id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A coordination thread already exists for this pair")

    thread = CoordinationThread(
        candidate_id=row.id,
        lead_bureau_id=uuid.UUID(body.lead_bureau_id) if body.lead_bureau_id else None,
        created_by=uuid.UUID(principal.user_id),
    )
    session.add(thread)
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="coordination_started",
        resource_type="overlap_candidate",
        resource_id=str(row.id),
    )
    await session.flush()
    return ThreadOut(
        id=str(thread.id),
        candidate_id=str(thread.candidate_id),
        lead_bureau_id=str(thread.lead_bureau_id) if thread.lead_bureau_id else None,
        status=thread.status,
        created_at=thread.created_at.isoformat(),
    )


def _require_thread_access(principal: Principal, thread: CoordinationThread, case_a: Case, case_b: Case, action: str) -> None:
    resource_bureau_ids = frozenset(
        str(b) for b in (case_a.assigned_bureau_id, case_b.assigned_bureau_id) if b
    )
    if not can(principal.role, action, actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted for this coordination thread")


async def _get_thread_or_404(session: AsyncSession, thread_id: str) -> CoordinationThread:
    row = (
        await session.execute(select(CoordinationThread).where(CoordinationThread.id == uuid.UUID(thread_id)))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Coordination thread not found")
    return row


class MessageOut(BaseModel):
    id: str
    author_role: str
    body: str
    created_at: str


class PostMessageRequest(BaseModel):
    body: str


@router.get("/overlap/threads/{thread_id}/messages", response_model=list[MessageOut])
async def list_messages(
    thread_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """RLS (not just `can()`) is the real boundary here — see the Phase
    4 migration's `coordination_messages_select` policy; this endpoint
    relies on that the same way `GET /cases/{id}/events` relies on
    `case_events`'s RLS (Section 4.3)."""
    thread = await _get_thread_or_404(session, thread_id)
    candidate = await _get_candidate_or_404(session, str(thread.candidate_id))
    case_a, case_b = await _get_cases(session, candidate.case_a_id, candidate.case_b_id)
    _require_thread_access(principal, thread, case_a, case_b, "overlap:coordinate")
    rows = (
        await session.execute(
            select(CoordinationMessage).where(CoordinationMessage.thread_id == thread.id).order_by(CoordinationMessage.created_at)
        )
    ).scalars().all()
    return [MessageOut(id=str(m.id), author_role=m.author_role, body=m.body, created_at=m.created_at.isoformat()) for m in rows]


@router.post(
    "/overlap/threads/{thread_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def post_message(
    thread_id: str,
    body: PostMessageRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not body.body.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message body is required")
    thread = await _get_thread_or_404(session, thread_id)
    candidate = await _get_candidate_or_404(session, str(thread.candidate_id))
    case_a, case_b = await _get_cases(session, candidate.case_a_id, candidate.case_b_id)
    _require_thread_access(principal, thread, case_a, case_b, "overlap:coordinate")
    message = CoordinationMessage(
        thread_id=thread.id,
        author_user_id=uuid.UUID(principal.user_id),
        author_role=principal.role,
        body=body.body,
    )
    session.add(message)
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="coordination_message_posted",
        resource_type="coordination_thread",
        resource_id=str(thread.id),
    )
    await session.flush()
    return MessageOut(id=str(message.id), author_role=message.author_role, body=message.body, created_at=message.created_at.isoformat())


class DecisionOut(BaseModel):
    id: str
    decision_type: str
    reason: str
    consolidate_bureau_id: str | None
    decided_at: str


class RecordDecisionRequest(BaseModel):
    decision_type: str
    reason: str
    consolidate_bureau_id: str | None = None


@router.post(
    "/overlap/threads/{thread_id}/decision",
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def record_decision(
    thread_id: str,
    body: RecordDecisionRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 8.5/R12: "proceed in parallel needs a reason" — this
    build requires a reason for every decision type (see
    `CoordinationDecision`'s docstring in app/models.py)."""
    if body.decision_type not in COORDINATION_DECISION_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown decision_type: {body.decision_type}")
    if not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A reason is required for every coordination decision")
    if body.decision_type == "consolidate" and not body.consolidate_bureau_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "consolidate_bureau_id is required for 'consolidate'")

    thread = await _get_thread_or_404(session, thread_id)
    candidate = await _get_candidate_or_404(session, str(thread.candidate_id))
    case_a, case_b = await _get_cases(session, candidate.case_a_id, candidate.case_b_id)
    _require_overlap_access(principal, case_a, case_b, "overlap:decide")

    decision = CoordinationDecision(
        thread_id=thread.id,
        decision_type=body.decision_type,
        reason=body.reason,
        consolidate_bureau_id=uuid.UUID(body.consolidate_bureau_id) if body.consolidate_bureau_id else None,
        decided_by=uuid.UUID(principal.user_id),
    )
    session.add(decision)
    thread.status = "closed"
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="coordination_decision_recorded",
        resource_type="coordination_thread",
        resource_id=str(thread.id),
    )
    await session.flush()
    return DecisionOut(
        id=str(decision.id),
        decision_type=decision.decision_type,
        reason=decision.reason,
        consolidate_bureau_id=str(decision.consolidate_bureau_id) if decision.consolidate_bureau_id else None,
        decided_at=decision.decided_at.isoformat(),
    )
