from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_plain_session() -> AsyncGenerator[AsyncSession, None]:
    """For routes that only touch identity tables not covered by
    user-scoped RLS (login, refresh, user self-lookup for building the
    RLS context itself — see core/deps.py)."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_privileged_session() -> AsyncGenerator[AsyncSession, None]:
    """For operations whose real authorization boundary is a `can()`
    check rather than row-level bureau/region scoping (e.g. the audit
    log, which `auditor`/`super_admin` read in full by definition).
    Every route using this still gates entry with `can(role, ...)`
    before the session is used for a query; this only sets `app.role`
    so RLS policies that key off it still see a real value, never an
    empty one."""
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        yield session


async def get_system_session() -> AsyncGenerator[AsyncSession, None]:
    """For server-side jobs that must read across every bureau's T2
    content by design (Section 4.1's `system` machine identity) —
    `scripts/rebuild_projection.py`'s replay and Phase 4's overlap-pair
    scoring (`app/services/overlap.py`), which needs both sides'
    registration descriptions to compute text similarity even though
    neither bureau could read the other's directly. `super_admin`
    deliberately cannot be used for this (Section 4.1: "No access to
    case content by default") — found as a real bug when
    `get_privileged_session`'s `app.role='super_admin'` was tried here
    first and silently returned zero case_events rows."""
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        yield session


async def get_tenant_session(
    *,
    user_id: str,
    role: str,
    bureau_ids: list[str],
    region_ids: list[str],
) -> AsyncGenerator[AsyncSession, None]:
    """Section 4.2 layer 3: every bureau/region-scoped query runs with
    SET LOCAL app.user_id/app.role/app.bureau_ids/app.region_ids set
    from the authenticated principal's real assignments (looked up
    server-side, never from client-supplied input) so Postgres RLS
    enforces the boundary regardless of what the service layer forgets
    to filter."""
    async with SessionLocal() as session, session.begin():
        # SET LOCAL doesn't accept bind parameters in Postgres;
        # set_config() is a regular function call and does.
        await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})
        await session.execute(text("SELECT set_config('app.role', :v, true)"), {"v": role})
        await session.execute(
            text("SELECT set_config('app.bureau_ids', :v, true)"), {"v": ",".join(bureau_ids)}
        )
        await session.execute(
            text("SELECT set_config('app.region_ids', :v, true)"), {"v": ",".join(region_ids)}
        )
        yield session
