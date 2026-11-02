import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import SavedView

router = APIRouter(prefix="/views", tags=["views"])


class SavedViewOut(BaseModel):
    id: str
    name: str
    filters: dict
    created_at: str


class SavedViewCreate(BaseModel):
    name: str
    filters: dict


@router.get("", response_model=list[SavedViewOut])
async def list_views(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 9.7's "saved views" — personal to the caller (Scope.SELF),
    same own-record pattern as `app/routers/sessions.py`."""
    if not can(principal.role, "view:manage", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (
        await session.execute(
            select(SavedView).where(SavedView.owner_id == uuid.UUID(principal.user_id)).order_by(SavedView.created_at)
        )
    ).scalars().all()
    return [
        SavedViewOut(id=str(v.id), name=v.name, filters=v.filters, created_at=v.created_at.isoformat()) for v in rows
    ]


@router.post("", response_model=SavedViewOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def create_view(
    body: SavedViewCreate,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "view:manage", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    view = SavedView(owner_id=uuid.UUID(principal.user_id), name=body.name, filters=body.filters)
    session.add(view)
    await session.flush()
    return SavedViewOut(id=str(view.id), name=view.name, filters=view.filters, created_at=view.created_at.isoformat())


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
async def delete_view(
    view_id: str,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "view:manage", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    result = await session.execute(
        delete(SavedView).where(SavedView.id == uuid.UUID(view_id), SavedView.owner_id == uuid.UUID(principal.user_id))
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved view not found")
