"""Integration test against the real Postgres in infra/docker-compose.yml
(requires `docker compose up -d postgres` first — see CI). Proves the
Phase 1 gate's "cross-bureau and cross-region leak tests" requirement
with real rows and real RLS, not a mocked permission check."""

import uuid

import pytest
from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Bureau, RegionalOffice, User, UserAssignment

from .db_helpers import OwnerSession


@pytest.fixture
async def two_bureaus_two_officers():
    bureau_a = uuid.uuid4()
    bureau_b = uuid.uuid4()
    region_a = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    async with OwnerSession() as session, session.begin():
        # icm_owner is non-superuser and subject to FORCE RLS on
        # users/user_assignments (Appendix A defect #5) — needed before
        # the User/UserAssignment inserts below.
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        session.add_all(
            [
                Bureau(id=bureau_a, name="RLS Test Bureau A", kind="bureau"),
                Bureau(id=bureau_b, name="RLS Test Bureau B", kind="bureau"),
                RegionalOffice(id=region_a, name="RLS Test Region A"),
            ]
        )
        session.add_all(
            [
                User(
                    id=user_a,
                    email=f"rls-a-{user_a}@example.test",
                    password_hash=hash_password("Correct-Horse-123-ab"),
                    role="bureau_head",
                    display_name="RLS Head A",
                    is_active=True,
                ),
                User(
                    id=user_b,
                    email=f"rls-b-{user_b}@example.test",
                    password_hash=hash_password("Correct-Horse-123-ab"),
                    role="bureau_head",
                    display_name="RLS Head B",
                    is_active=True,
                ),
            ]
        )
        session.add_all(
            [
                UserAssignment(user_id=user_a, bureau_id=bureau_a),
                UserAssignment(user_id=user_b, bureau_id=bureau_b),
            ]
        )

    yield {"bureau_a": bureau_a, "bureau_b": bureau_b, "region_a": region_a, "user_a": user_a, "user_b": user_b}

    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        await session.execute(
            text("DELETE FROM user_assignments WHERE user_id IN (:a, :b)"), {"a": user_a, "b": user_b}
        )
        await session.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": user_a, "b": user_b})
        await session.execute(
            text("DELETE FROM bureaus WHERE id IN (:a, :b)"), {"a": bureau_a, "b": bureau_b}
        )
        await session.execute(text("DELETE FROM regional_offices WHERE id = :r"), {"r": region_a})


async def test_bureau_head_cannot_see_users_in_a_different_bureau(two_bureaus_two_officers):
    """The actual leak scenario: bureau_head A must not be able to
    enumerate bureau_head B's row via a plain SELECT, even with no
    application-level filter — RLS is the backstop."""
    d = two_bureaus_two_officers
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'bureau_head', true)"))
        await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": str(d["user_a"])})
        await session.execute(
            text("SELECT set_config('app.bureau_ids', :v, true)"), {"v": str(d["bureau_a"])}
        )
        await session.execute(text("SELECT set_config('app.region_ids', :v, true)"), {"v": ""})
        rows = (await session.execute(text("SELECT id FROM users"))).all()

    seen = {str(r[0]) for r in rows}
    assert str(d["user_a"]) in seen, "a bureau head must see their own row"
    assert str(d["user_b"]) not in seen, "RLS leak: bureau A saw bureau B's user"


async def test_regional_officer_scoping_is_independent_of_bureau_scoping(two_bureaus_two_officers):
    """A region-scoped principal with no bureau_ids must not fall back to
    seeing bureau-scoped rows (no accidental OR-everything bug)."""
    d = two_bureaus_two_officers
    async with SessionLocal() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'regional_officer', true)"))
        await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": str(uuid.uuid4())})
        await session.execute(text("SELECT set_config('app.bureau_ids', :v, true)"), {"v": ""})
        await session.execute(
            text("SELECT set_config('app.region_ids', :v, true)"), {"v": str(d["region_a"])}
        )
        rows = (await session.execute(text("SELECT id FROM users"))).all()

    seen = {str(r[0]) for r in rows}
    assert str(d["user_a"]) not in seen
    assert str(d["user_b"]) not in seen


async def test_elevated_roles_see_both_bureaus(two_bureaus_two_officers):
    d = two_bureaus_two_officers
    for role in ("super_admin", "competent_authority", "senior_management", "auditor", "nodal_pg_officer"):
        async with SessionLocal() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', :v, true)"), {"v": role})
            await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": str(uuid.uuid4())})
            await session.execute(text("SELECT set_config('app.bureau_ids', :v, true)"), {"v": ""})
            await session.execute(text("SELECT set_config('app.region_ids', :v, true)"), {"v": ""})
            rows = (await session.execute(text("SELECT id FROM users"))).all()
        seen = {str(r[0]) for r in rows}
        assert {str(d["user_a"]), str(d["user_b"])} <= seen, f"{role} should see every bureau"


async def test_no_session_context_set_sees_nothing(two_bureaus_two_officers):
    """Fail closed: a request path that forgot to set the RLS session
    vars must get zero rows, never the unfiltered table."""
    async with SessionLocal() as session, session.begin():
        rows = (await session.execute(text("SELECT id FROM users"))).all()
    assert rows == []


def test_icm_app_role_cannot_update_or_delete_audit_log():
    """Proven against the real DATABASE_URL credential (icm_app), not
    just application code behaving itself (Section 7.4's append-only
    guarantee)."""
    import psycopg

    from app.core.config import settings

    conn = psycopg.connect(settings.database_url.replace("postgresql+psycopg://", "postgresql://"))
    try:
        with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("UPDATE audit_log SET action = 'x' WHERE false")
        conn.rollback()
        with conn.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM audit_log WHERE false")
    finally:
        conn.rollback()
        conn.close()


def test_audit_log_trigger_blocks_even_the_owner_role():
    """Defense in depth beyond the GRANT: the BEFORE UPDATE/DELETE
    trigger rejects mutation regardless of which role attempts it. Runs
    the insert-then-delete-then-rollback inside one uncommitted
    transaction so the probe row never actually persists — audit_log is
    genuinely append-only forever, including for this test."""
    import psycopg

    from app.core.config import settings

    owner_dsn = settings.migration_database_url.replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(owner_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (id, actor_role, action, resource_type, resource_id, prev_hash, row_hash) "
                "VALUES (gen_random_uuid(), 'system', 'rls_trigger_probe', 'test', '1', repeat('0',64), repeat('1',64)) "
                "RETURNING id"
            )
            probe_id = cur.fetchone()[0]
            with pytest.raises(psycopg.errors.RaiseException):
                cur.execute("DELETE FROM audit_log WHERE id = %s", (probe_id,))
    finally:
        conn.rollback()  # never commit the probe row
        conn.close()
