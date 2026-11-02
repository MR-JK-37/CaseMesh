import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import RefreshTokenFamily
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    id: str
    device_label: str | None
    created_at: str
    last_used_at: str | None
    revoked: bool


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 4.1: device/session list with remote sign-out. Scoped to
    the caller's own sessions — there is no action in Phase 1's matrix
    for viewing another user's sessions."""
    if not can(principal.role, "session:list_own", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    rows = (
        await session.execute(
            select(RefreshTokenFamily)
            .where(RefreshTokenFamily.user_id == uuid.UUID(principal.user_id))
            .order_by(RefreshTokenFamily.created_at.desc())
        )
    ).scalars().all()
    return [
        SessionOut(
            id=str(r.id),
            device_label=r.device_label,
            created_at=r.created_at.isoformat(),
            last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
            revoked=r.revoked,
        )
        for r in rows
    ]


@router.post(
    "/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def revoke_session(
    session_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "session:revoke_own", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    family = (
        await session.execute(select(RefreshTokenFamily).where(RefreshTokenFamily.id == uuid.UUID(session_id)))
    ).scalar_one_or_none()
    # 404 for a session that isn't the caller's own (no existence leak,
    # Section 4.2), not 403.
    if family is None or str(family.user_id) != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    family.revoked = True
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="session_revoked",
        resource_type="refresh_token_family",
        resource_id=session_id,
    )
