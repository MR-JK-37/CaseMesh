from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.deps import Principal, get_current_principal, get_scoped_session
from app.models import Bureau, RegionalOffice

router = APIRouter(tags=["reference"])


class BureauOut(BaseModel):
    id: str
    name: str
    kind: str
    source_name: str | None
    source_url: str | None


@router.get("/bureaus", response_model=list[BureauOut])
async def list_bureaus(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "bureau:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (await session.execute(select(Bureau).order_by(Bureau.name))).scalars().all()
    return [
        BureauOut(id=str(r.id), name=r.name, kind=r.kind, source_name=r.source_name, source_url=r.source_url)
        for r in rows
    ]


class RegionOut(BaseModel):
    id: str
    name: str
    source_name: str | None
    source_url: str | None


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "region:list"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (await session.execute(select(RegionalOffice).order_by(RegionalOffice.name))).scalars().all()
    return [
        RegionOut(id=str(r.id), name=r.name, source_name=r.source_name, source_url=r.source_url)
        for r in rows
    ]
