from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session
from app.services.dashboard import compute_monthly_series, compute_tiles

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/tiles")
async def dashboard_tiles(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 6.5/9.6's Command Dashboard tiles — reuses `case:list`'s
    permission (dashboard tiles are aggregates over the same T1
    coordination metadata `GET /cases` already exposes to every
    authenticated official, never case content), so there is no
    separate `dashboard:read` action to keep in sync with it."""
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    return await compute_tiles(session)


@router.get("/monthly")
async def dashboard_monthly(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "case:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    return await compute_monthly_series(session)
