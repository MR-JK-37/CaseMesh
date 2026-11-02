"""Shared test-only DB helper: an owner-role session for fixture setup/
teardown. Tests must exercise the real icm_app least-privilege role for
anything that simulates an actual request path (that's the whole point
of the RLS/grant tests) — but fixture setup/teardown for tables icm_app
has no write/delete grant on (bureaus, regional_offices,
user_assignments deletes, users deletes) legitimately needs the owner
role, the same way a real migration or admin tool would."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings

_owner_engine = create_async_engine(settings.migration_database_url)
OwnerSession = async_sessionmaker(_owner_engine, expire_on_commit=False)
