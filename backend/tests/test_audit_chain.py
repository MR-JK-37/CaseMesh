"""Integration test against the real Postgres (docker compose up -d
postgres). Section 7.4/M14: hash chain append + on-demand verification,
and real tamper detection.

audit_log is genuinely append-only forever (trigger + no grant — see
test_rls_leak.py), which means a naive tamper test that commits a
tampered row would permanently break verify_chain() for every later
test run against this dev database. The tamper scenario below runs
inside one transaction, bound to the owner role (DROP/CREATE TRIGGER
needs table-owner privileges), and is always rolled back at the end —
nothing it does is ever committed.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.audit import append_audit_entry, verify_chain

_owner_engine = create_async_engine(settings.migration_database_url)
_OwnerSession = async_sessionmaker(_owner_engine, expire_on_commit=False)


async def test_appending_entries_keeps_the_chain_intact():
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        assert await verify_chain(session) is True
        for i in range(3):
            await append_audit_entry(
                session,
                actor_user_id=None,
                actor_role="system",
                action=f"test:chain:{i}",
                resource_type="test",
                resource_id=str(i),
            )
        assert await verify_chain(session) is True


async def test_tampering_is_detected_by_verify_chain():
    """Everything here runs in one never-committed transaction: append a
    real entry, temporarily drop the anti-tamper trigger, tamper the
    row, prove verify_chain() independently catches it (a second
    detection layer beyond the trigger), restore the trigger, then roll
    back so none of this — including the tamper itself — persists."""
    session = _OwnerSession()
    try:
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        entry = await append_audit_entry(
            session,
            actor_user_id=None,
            actor_role="system",
            action="test:tamper_target",
            resource_type="test",
            resource_id=str(uuid.uuid4()),
        )
        assert await verify_chain(session) is True

        await session.execute(text("DROP TRIGGER audit_log_no_update ON audit_log"))
        await session.execute(
            text("UPDATE audit_log SET action = 'tampered' WHERE id = :id"), {"id": entry.id}
        )
        # The raw UPDATE above bypasses the ORM, so the session's
        # identity map still holds `entry`'s pre-tamper attribute values
        # (SQLAlchemy doesn't refresh already-loaded objects by default)
        # — expire it so verify_chain's SELECT re-reads the real row.
        session.expire_all()
        assert await verify_chain(session) is False, "verify_chain must detect the tampered row"

        await session.execute(
            text(
                "CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()"
            )
        )
    finally:
        await session.rollback()
        await session.close()
