import uuid

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.config import settings
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.models import User
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/totp", tags=["totp"])


class EnrollStartResponse(BaseModel):
    secret: str
    provisioning_uri: str


@router.post("/enroll/start", response_model=EnrollStartResponse)
async def enroll_start(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Generates a new TOTP secret but does not activate it yet — Section
    4.1 enrollment is two-step (start, then confirm with a real code) so
    a user can't lock themselves out by saving a secret they can't
    actually produce codes for."""
    if not can(principal.role, "totp:enroll_self", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    user = (
        await session.execute(select(User).where(User.id == uuid.UUID(principal.user_id)))
    ).scalar_one()
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enrolled_at = None  # not confirmed yet
    await session.flush()

    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.totp_issuer)
    return EnrollStartResponse(secret=secret, provisioning_uri=uri)


class EnrollConfirmRequest(BaseModel):
    totp_code: str


@router.post("/enroll/confirm", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
async def enroll_confirm(
    body: EnrollConfirmRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "totp:enroll_self", is_own_record=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")

    user = (
        await session.execute(select(User).where(User.id == uuid.UUID(principal.user_id)))
    ).scalar_one()
    if not user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Call /totp/enroll/start first")
    if not pyotp.TOTP(user.totp_secret).verify(body.totp_code, valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code")

    import datetime as dt

    user.totp_enrolled_at = dt.datetime.now(dt.UTC)
    await append_audit_entry(
        session,
        actor_user_id=user.id,
        actor_role=principal.role,
        action="totp_enrolled",
        resource_type="user",
        resource_id=str(user.id),
    )
