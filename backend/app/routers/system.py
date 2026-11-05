from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfoOut(BaseModel):
    tenant_mode: str
    version: str = "0.1.0"
    app_name: str = "CaseMesh"


@router.get("/info", response_model=SystemInfoOut)
async def system_info():
    """Unauthenticated on purpose: the TEST sandbox banner (Section
    1.4(b)) must render on the sign-in screen too, before any session
    exists."""
    return SystemInfoOut(
        tenant_mode=settings.tenant_mode,
        version=settings.app_version,
        app_name=settings.project_name,
    )
