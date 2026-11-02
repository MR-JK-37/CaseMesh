import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import Alert, Case, OverlapCandidate
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(BaseModel):
    id: str
    code: str
    severity: str
    resource_type: str
    resource_id: str | None
    message: str
    created_at: str
    acked_by: str | None
    acked_at: str | None


def _to_out(a: Alert) -> AlertOut:
    return AlertOut(
        id=str(a.id),
        code=a.code,
        severity=a.severity,
        resource_type=a.resource_type,
        resource_id=str(a.resource_id) if a.resource_id else None,
        message=a.message,
        created_at=a.created_at.isoformat(),
        acked_by=str(a.acked_by) if a.acked_by else None,
        acked_at=a.acked_at.isoformat() if a.acked_at else None,
    )


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    unacked_only: bool = False,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 7.3: alerts are structured, non-sensitive T1-equivalent
    metadata (see `Alert`'s docstring in app/models.py) — broadly
    listable so `SLA_POLICY_MISSING` reaches `super_admin`, who has no
    case-content access by design."""
    if not can(principal.role, "alert:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    query = select(Alert).order_by(Alert.created_at.desc())
    if unacked_only:
        query = query.where(Alert.acked_at.is_(None))
    rows = (await session.execute(query)).scalars().all()
    return [_to_out(a) for a in rows]


@router.post("/{alert_id}/ack", response_model=AlertOut, dependencies=[Depends(require_csrf)])
async def ack_alert(
    alert_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    alert = (await session.execute(select(Alert).where(Alert.id == uuid.UUID(alert_id)))).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")

    # Section 7.3's OWN_BUREAU-scoped alert codes (ESCALATION_RAISED,
    # SLA_APPROACHING/BREACHED, CASE_STALE, TRANSFER_UNACCEPTED) carry
    # resource_type="case"; the overlap-engine codes (OVERLAP_DETECTED,
    # OVERLAP_HIGH_CONFIDENCE) carry resource_type="overlap_candidate"
    # instead — found as a real gap by actually trying to acknowledge
    # one in the browser: every overlap alert silently 403'd for every
    # bureau_head, because this resolution only ever checked "case",
    # never the candidate's own two member cases' bureaus (the exact
    # union app/routers/overlap.py's `_require_overlap_access` already
    # uses for confirm/dismiss/coordinate/decide on the same resource).
    resource_bureau_ids: frozenset[str] = frozenset()
    if alert.resource_type == "case" and alert.resource_id:
        case = (await session.execute(select(Case).where(Case.id == alert.resource_id))).scalar_one_or_none()
        if case and case.assigned_bureau_id:
            resource_bureau_ids = frozenset({str(case.assigned_bureau_id)})
    elif alert.resource_type == "overlap_candidate" and alert.resource_id:
        candidate = (
            await session.execute(select(OverlapCandidate).where(OverlapCandidate.id == alert.resource_id))
        ).scalar_one_or_none()
        if candidate is not None:
            cases = (
                await session.execute(select(Case).where(Case.id.in_([candidate.case_a_id, candidate.case_b_id])))
            ).scalars().all()
            resource_bureau_ids = frozenset(str(c.assigned_bureau_id) for c in cases if c.assigned_bureau_id)

    if not can(principal.role, "alert:ack", actor_bureau_ids=principal.bureau_ids, resource_bureau_ids=resource_bureau_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    if alert.acked_at is None:
        alert.acked_by = uuid.UUID(principal.user_id)
        alert.acked_at = dt.datetime.now(dt.UTC)
        await append_audit_entry(
            session,
            actor_user_id=uuid.UUID(principal.user_id),
            actor_role=principal.role,
            action="alert_acked",
            resource_type="alert",
            resource_id=str(alert.id),
        )
        await session.flush()
    return _to_out(alert)
