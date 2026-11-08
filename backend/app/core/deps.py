from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, get_tenant_session
from app.core.security import decode_token
from app.models import User, UserAssignment

ACCESS_COOKIE = "icm_access"
CSRF_COOKIE = "icm_csrf"
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    bureau_ids: frozenset[str] = field(default_factory=frozenset)
    region_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    @property
    def is_auditor(self) -> bool:
        return self.role == "auditor"

    @property
    def is_bureau_head(self) -> bool:
        return self.role == "bureau_head"

    @property
    def is_case_officer(self) -> bool:
        return self.role == "case_officer"


async def get_current_principal(
    icm_access: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> Principal:
    """Section 7.4: the web session is an HttpOnly cookie, never a token
    kept in JS memory (the prior build's defect — it logged users out on
    every refresh). Looks up the user's current bureau/region assignments
    fresh from the DB on every request, not from the token, so a
    reassignment is effective immediately (see core/security.py)."""
    if not icm_access:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(icm_access)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from None
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    user_id = payload["sub"]
    role = payload["role"]

    async with SessionLocal() as session, session.begin():
        # user_assignments has FORCE ROW LEVEL SECURITY (Phase 1) with a
        # self-visibility clause — without setting app.user_id first,
        # this SELECT silently returned zero rows for every principal
        # regardless of role, which meant every OWN_BUREAU-scoped
        # permission check failed for everyone, always. A real bug
        # found when Phase 3's case:register (bureau_head,
        # Scope.OWN_BUREAU) started actually exercising this path
        # through a live HTTP request — see docs/decision-log.md.
        await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})
        rows = (
            await session.execute(
                select(UserAssignment.bureau_id, UserAssignment.region_id).where(
                    UserAssignment.user_id == user_id
                )
            )
        ).all()
    bureau_ids = frozenset(str(r[0]) for r in rows if r[0] is not None)
    region_ids = frozenset(str(r[1]) for r in rows if r[1] is not None)

    return Principal(user_id=user_id, role=role, bureau_ids=bureau_ids, region_ids=region_ids)


async def get_scoped_session(
    principal: Principal = Depends(get_current_principal),
) -> AsyncGenerator[AsyncSession, None]:
    async for session in get_tenant_session(
        user_id=principal.user_id,
        role=principal.role,
        bureau_ids=list(principal.bureau_ids),
        region_ids=list(principal.region_ids),
    ):
        yield session


def require_csrf(
    request: Request,
    icm_csrf: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    x_csrf_token: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    """Double-submit CSRF check for every state-changing request (Section
    7.4). The cookie alone can't be read by an attacker's cross-site
    request (it's a plain, non-HttpOnly cookie read by our own frontend
    JS to echo back in the header) — only a same-origin page can read the
    cookie value to put it in the header."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not icm_csrf or not x_csrf_token or icm_csrf != x_csrf_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")


async def require_step_up(
    icm_step_up: str | None = Cookie(default=None, alias="icm_step_up"),
    principal: Principal = Depends(get_current_principal),
) -> None:
    """Section 4.1: fresh TOTP re-verification required for sensitive
    actions. Not yet wired to any Phase 1 endpoint (transfer/escalation/
    disposal/confidential-export/role-change don't exist yet) — exported
    for Phase 3+ to depend on; `routers/auth.py`'s `/auth/step-up`
    endpoint issues the cookie this checks."""
    if not icm_step_up:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "Step-up verification required")
    try:
        payload = decode_token(icm_step_up)
    except ValueError:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "Step-up verification expired") from None
    if payload.get("type") != "step_up" or payload.get("sub") != principal.user_id:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "Step-up verification required")


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
