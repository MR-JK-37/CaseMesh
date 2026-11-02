from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfoOut(BaseModel):
    tenant_mode: str


@router.get("/info", response_model=SystemInfoOut)
async def system_info():
    """Unauthenticated on purpose: the TEST sandbox banner (Section
    1.4(b)) must render on the sign-in screen too, before any session
    exists."""
    return SystemInfoOut(tenant_mode=settings.tenant_mode)
