import datetime as dt
import uuid
from typing import NoReturn

import pyotp
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_privileged_session
from app.core.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    Principal,
    get_current_principal,
    get_scoped_session,
    require_csrf,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_step_up_token,
    decode_token,
    generate_csrf_token,
    verify_password,
)
from app.core.valkey import get_valkey_client
from app.models import TOTP_REQUIRED_ROLES, LoginAttempt, RefreshTokenFamily, User
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()

REFRESH_COOKIE = "icm_refresh"
STEP_UP_COOKIE = "icm_step_up"


class LoginRequest(BaseModel):
    email: str
    password: str
    totp_code: str | None = None


class TotpStepRequiredResponse(BaseModel):
    totp_required: bool = True
    totp_enrolled: bool


class LoginOkResponse(BaseModel):
    user_id: str
    role: str
    csrf_token: str


def _ip_prefix(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    # Section 6.4's "bound to user and IP prefix" pattern reused for rate
    # limiting: /24 for IPv4, coarse enough to not fingerprint a single
    # user behind a shared NAT while still bucketing abuse.
    parts = host.split(".")
    return ".".join(parts[:3]) if len(parts) == 4 else host


async def _check_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    """Fixed-window limiter via Valkey INCR+EXPIRE (Section 7.4 asks for a
    "sliding window"; this is a simpler fixed window — an honest
    simplification, noted in docs/decision-log.md, not claimed as the
    stronger guarantee)."""
    client = get_valkey_client()
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, window_seconds)
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")


def _set_auth_cookies(response: Response, *, access: str, refresh: str) -> str:
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        httponly=True,
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path="/api/v1/auth",
    )
    csrf = generate_csrf_token()
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,  # frontend JS must read this to echo it back in a header
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path="/",
    )
    return csrf


@router.post("/login", response_model=LoginOkResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_privileged_session),
):
    await _check_rate_limit(f"ratelimit:login:{_ip_prefix(request)}", limit=20, window_seconds=600)
    await _check_rate_limit(f"ratelimit:login:{body.email}", limit=10, window_seconds=600)

    user = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()

    async def fail(status_code: int, detail: str, reason: str) -> NoReturn:
        # `get_privileged_session` rolls back on any exception raised
        # through its generator's yield point — correct for routes whose
        # failure path should discard everything, wrong here, since a
        # failed login's lockout counter and LoginAttempt row must
        # persist even though the request ends in an HTTPException.
        # Commit explicitly before raising, same pattern /refresh uses
        # for reuse-detection revocation.
        session.add(
            LoginAttempt(
                email=body.email, success=False, reason=reason, ip_prefix=_ip_prefix(request)
            )
        )
        await session.commit()
        raise HTTPException(status_code, detail)

    if user is None or not user.is_active:
        await fail(status.HTTP_401_UNAUTHORIZED, "Invalid credentials", "no_such_user_or_inactive")

    now = dt.datetime.now(dt.UTC)
    if user.locked_until and user.locked_until > now:
        await fail(status.HTTP_423_LOCKED, "Account temporarily locked; try again later", "locked")

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.lockout_threshold:
            user.locked_until = now + dt.timedelta(minutes=settings.lockout_window_minutes)
        await fail(status.HTTP_401_UNAUTHORIZED, "Invalid credentials", "bad_password")

    if user.role in TOTP_REQUIRED_ROLES:
        if not user.totp_secret:
            await fail(
                status.HTTP_412_PRECONDITION_FAILED,
                "TOTP enrollment required for this role",
                "totp_enrollment_required",
            )
        # valid_window=1 tolerates one 30s step of clock/processing skew
        # either side of "now" — standard TOTP practice, and a real fix:
        # zero tolerance meant a code generated and verified a few
        # hundred ms apart could straddle a window boundary and fail
        # with "Invalid credentials" for no real reason, a flake this
        # session's slower (more DB work per request) full suite runs
        # made frequent enough to notice — see docs/decision-log.md.
        if not body.totp_code or not pyotp.TOTP(user.totp_secret).verify(body.totp_code, valid_window=1):
            user.failed_login_count += 1
            if user.failed_login_count >= settings.lockout_threshold:
                user.locked_until = now + dt.timedelta(minutes=settings.lockout_window_minutes)
            await fail(status.HTTP_401_UNAUTHORIZED, "Invalid credentials", "bad_totp")

    user.failed_login_count = 0
    user.locked_until = None
    session.add(LoginAttempt(email=body.email, success=True, reason=None, ip_prefix=_ip_prefix(request)))

    family = RefreshTokenFamily(user_id=user.id, current_version=1)
    session.add(family)
    await session.flush()

    await append_audit_entry(
        session,
        actor_user_id=user.id,
        actor_role=user.role,
        action="login",
        resource_type="user",
        resource_id=str(user.id),
    )

    access = create_access_token(user_id=user.id, role=user.role)
    refresh = create_refresh_token(family_id=family.id, version=family.current_version)
    csrf = _set_auth_cookies(response, access=access, refresh=refresh)
    return LoginOkResponse(user_id=str(user.id), role=user.role, csrf_token=csrf)


@router.post("/refresh", response_model=LoginOkResponse)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_privileged_session),
):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh cookie")
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")

    family_id = uuid.UUID(payload["family"])
    family = (
        await session.execute(select(RefreshTokenFamily).where(RefreshTokenFamily.id == family_id))
    ).scalar_one_or_none()
    if family is None or family.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked")

    if payload["version"] != family.current_version:
        # Reuse of an already-rotated-away token: revoke the whole
        # family (Section 4.1), not just reject this one request.
        family.revoked = True
        await session.commit()
        log.warning("refresh_token_reuse_detected", family_id=str(family_id))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected; session revoked")

    user = (await session.execute(select(User).where(User.id == family.user_id))).scalar_one()

    family.current_version += 1
    family.last_used_at = dt.datetime.now(dt.UTC)
    await session.flush()

    access = create_access_token(user_id=user.id, role=user.role)
    new_refresh = create_refresh_token(family_id=family.id, version=family.current_version)
    csrf = _set_auth_cookies(response, access=access, refresh=new_refresh)
    return LoginOkResponse(user_id=str(user.id), role=user.role, csrf_token=csrf)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
async def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") == "refresh":
                family = (
                    await session.execute(
                        select(RefreshTokenFamily).where(
                            RefreshTokenFamily.id == uuid.UUID(payload["family"])
                        )
                    )
                ).scalar_one_or_none()
                if family:
                    family.revoked = True
        except ValueError:
            pass

    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="logout",
        resource_type="user",
        resource_id=principal.user_id,
    )

    for cookie in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE, STEP_UP_COOKIE):
        response.delete_cookie(cookie, path="/")


class StepUpRequest(BaseModel):
    totp_code: str


@router.post("/step-up", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
async def step_up(
    body: StepUpRequest,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Section 4.1: re-verify TOTP to mint a short-lived step-up cookie
    that sensitive endpoints (transfer, escalation, disposal, ...) will
    require once those endpoints exist (Phase 3+)."""
    user = (
        await session.execute(select(User).where(User.id == uuid.UUID(principal.user_id)))
    ).scalar_one()
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(body.totp_code, valid_window=1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid TOTP code")

    token = create_step_up_token(user_id=user.id)
    response.set_cookie(
        STEP_UP_COOKIE,
        token,
        httponly=True,
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=settings.step_up_ttl_minutes * 60,
        path="/",
    )
