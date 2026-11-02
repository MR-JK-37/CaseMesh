import datetime as dt
import uuid

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.policy import can
from app.core.config import settings
from app.core.deps import Principal, get_current_principal, get_scoped_session, require_csrf
from app.core.security import hash_password
from app.models import ROLES, TOTP_REQUIRED_ROLES, User, UserAssignment
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    totp_enrolled: bool


def _to_out(u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        is_active=u.is_active,
        totp_enrolled=u.totp_enrolled_at is not None,
    )


@router.get("", response_model=list[UserOut])
async def list_users(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    """Scope is enforced twice (Section 4.2 layers 1 and 3): `can()`
    gates entry to the action at all, and Postgres RLS on `users`
    (Phase 1 migration) independently filters which rows come back even
    if this query forgot a WHERE clause.

    For an OWN_BUREAU-scoped role, "list" means "list within my own
    bureau" — resource_bureau_ids is the actor's own bureau_ids, which
    trivially satisfies the intersection check in `can()`. Omitting this
    (as a previous version of this endpoint did) makes `actor_bureau_ids
    & resource_bureau_ids` always empty, silently 403-ing every
    OWN_BUREAU-scoped role regardless of real bureau membership — found
    via Phase 3's case-assignment dropdown, which depends on this
    endpoint and was returning zero candidates for every bureau_head."""
    if not can(
        principal.role,
        "user:list",
        actor_bureau_ids=principal.bureau_ids,
        resource_bureau_ids=principal.bureau_ids,
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    rows = (await session.execute(select(User).order_by(User.email))).scalars().all()
    return [_to_out(u) for u in rows]


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    role: str
    bureau_ids: list[str] = []
    region_ids: list[str] = []


class CreateUserResponse(UserOut):
    totp_provisioning_uri: str | None = None


@router.post(
    "", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_user(
    body: CreateUserRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "user:create"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    if body.role not in ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown role: {body.role}")
    if len(body.password) < 12:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password must be at least 12 characters")

    existing = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")

    # Section 4.1: TOTP-required roles can't self-enroll on first login
    # (enrollment needs an authenticated session, which needs TOTP
    # already set up for those roles — a real chicken-and-egg found
    # while building the login flow, see docs/decision-log.md). The
    # admin creating the account pre-provisions the secret here and
    # hands the provisioning URI to the new user out-of-band, the same
    # pattern scripts/seed_dev.py uses for the bootstrap super_admin.
    totp_secret = pyotp.random_base32() if body.role in TOTP_REQUIRED_ROLES else None

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        totp_secret=totp_secret,
        totp_enrolled_at=dt.datetime.now(dt.UTC) if totp_secret else None,
    )
    session.add(user)
    await session.flush()

    for bureau_id in body.bureau_ids:
        session.add(UserAssignment(user_id=user.id, bureau_id=uuid.UUID(bureau_id)))
    for region_id in body.region_ids:
        session.add(UserAssignment(user_id=user.id, region_id=uuid.UUID(region_id)))

    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="user_created",
        resource_type="user",
        resource_id=str(user.id),
    )
    await session.flush()

    uri = (
        pyotp.TOTP(totp_secret).provisioning_uri(name=user.email, issuer_name=settings.totp_issuer)
        if totp_secret
        else None
    )
    return CreateUserResponse(**_to_out(user).model_dump(), totp_provisioning_uri=uri)


class AssignRequest(BaseModel):
    bureau_id: str | None = None
    region_id: str | None = None


@router.post("/{user_id}/assignments", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def add_assignment(
    user_id: str,
    body: AssignRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_scoped_session),
):
    if not can(principal.role, "user:assign"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    if not body.bureau_id and not body.region_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bureau_id or region_id required")

    target = (await session.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    assignment = UserAssignment(
        user_id=target.id,
        bureau_id=uuid.UUID(body.bureau_id) if body.bureau_id else None,
        region_id=uuid.UUID(body.region_id) if body.region_id else None,
    )
    session.add(assignment)
    await append_audit_entry(
        session,
        actor_user_id=uuid.UUID(principal.user_id),
        actor_role=principal.role,
        action="user_assigned",
        resource_type="user",
        resource_id=user_id,
    )
