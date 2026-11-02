from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.db import get_privileged_session
from app.core.deps import Principal, get_current_principal
from app.models import AuditLogEntry
from app.services.audit import verify_chain

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit_log(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_privileged_session),
):
    if not can(principal.role, "audit:read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (
        await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.seq.desc()).limit(200))
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
            "actor_role": r.actor_role,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/verify-chain")
async def verify_audit_chain(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_privileged_session),
):
    """On-demand proof the hash chain hasn't been tampered with (Section
    7.4/M14). The daily external-anchor job is
    `backend/scripts/anchor_audit_chain.py`, separate from this
    on-demand recompute."""
    if not can(principal.role, "audit:read"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    return {"intact": await verify_chain(session)}
