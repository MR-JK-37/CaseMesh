"""Integration tests against the real Postgres + the real FastAPI app.
Drives actual HTTP requests through the actual role/bureau RLS boundary
— register, duplicate-check, workflow actions, T1/T2 visibility,
counter reconciliation, and (via scripts.rebuild_projection) projection
replay equality. Section 16 Phase 3 gate: "R3 and R8 tests; projection
replay equality; counter reconciliation."

Each logged-in user gets its own `TestClient` (own cookie jar) —
`starlette.testclient.TestClient` has no per-request cookie override, so
a single shared client's session gets silently hijacked by whichever
user logged in most recently, a real bug this file's first draft hit
(multi-user tests like transfer propose/accept need two sessions live
at once — see docs/decision-log.md).
"""

import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password
from app.core.valkey import get_valkey_client
from app.main import app
from app.models import TOTP_REQUIRED_ROLES, Bureau, Institution, User, UserAssignment

from .db_helpers import OwnerSession

PASSWORD = "Correct-Horse-Battery-Staple-9"


@pytest.fixture(autouse=True)
async def _reset_rate_limit_buckets():
    yield
    r = get_valkey_client()
    async for key in r.scan_iter("ratelimit:login:*"):
        await r.delete(key)


class Session:
    """A logged-in user: its own TestClient + CSRF header."""

    def __init__(self, user_id: uuid.UUID, client: TestClient, csrf: str):
        self.user_id = user_id
        self.client = client
        self.headers = {"X-CSRF-Token": csrf}


async def _login_as(role: str, *, bureau_id: uuid.UUID | None = None) -> Session:
    user_id = uuid.uuid4()
    email = f"{role}-{user_id}@example.test"
    totp_secret = pyotp.random_base32() if role in TOTP_REQUIRED_ROLES else None
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=role,
                display_name=role,
                is_active=True,
                totp_secret=totp_secret,
            )
        )
        if bureau_id:
            session.add(UserAssignment(user_id=user_id, bureau_id=bureau_id))
    body = {"email": email, "password": PASSWORD}
    if totp_secret:
        body["totp_code"] = pyotp.TOTP(totp_secret).now()
    client = TestClient(app)
    resp = client.post("/api/v1/auth/login", json=body)
    assert resp.status_code == 200, resp.text
    return Session(user_id, client, resp.cookies["icm_csrf"])


@pytest.fixture
async def world():
    """One institution and two bureaus — enough surface for transfer,
    T1/T2 visibility, and duplicate-check tests."""
    bureau_a = uuid.uuid4()
    bureau_b = uuid.uuid4()
    inst_id = uuid.uuid4()
    async with OwnerSession() as session, session.begin():
        session.add_all(
            [
                Bureau(id=bureau_a, name="Cases Test Bureau A", kind="bureau"),
                Bureau(id=bureau_b, name="Cases Test Bureau B", kind="bureau"),
                Institution(
                    id=inst_id,
                    permanent_id=f"1-{uuid.uuid4().int % 900000000 + 100000000}",
                    name="Cases Test Institute",
                    status="active",
                    data_origin="user_entered",
                    source_name="test fixture",
                ),
            ]
        )
    # No teardown delete: case_events is append-only (same guarantee as
    # audit_log, Section 6.3), and cases.registered_by/
    # case_events.actor_user_id have no ON DELETE CASCADE — so any
    # institution, bureau, or user that ever participates in a
    # registered case becomes permanently undeletable by design (found
    # as a real FK/trigger failure in this test's own first draft, not
    # anticipated — docs/decision-log.md). That's correct production
    # behavior (cases are permanent records), so tests that touch the
    # case lifecycle accept the same permanent rows audit_log's tests
    # already do, rather than fighting the guarantee.
    yield {"bureau_a": bureau_a, "bureau_b": bureau_b, "institution": inst_id}


async def _cleanup_user(user_id: uuid.UUID) -> None:
    """Best-effort: a user who never touched a case gets fully removed;
    one who authored a case_events row is left in place (see `world`'s
    docstring)."""
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        await session.execute(text("DELETE FROM refresh_token_families WHERE user_id = :id"), {"id": user_id})
    import contextlib

    with contextlib.suppress(Exception):  # FK-referenced-by-case_events is expected, not a bug
        async with OwnerSession() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
            await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def _register_body(world, bureau_id, **overrides):
    body = {
        "institution_ids": [str(world["institution"])],
        "matter_type": "ragging",
        "source_channel": "letter",
        "assigned_bureau_id": str(bureau_id),
    }
    body.update(overrides)
    return body


async def test_register_case_sets_mandatory_r3_fields(world):
    u = await _login_as("registry_operator")
    try:
        resp = u.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=u.headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["case_number"].startswith("ICM-")
        assert body["status"] == "pending"
        assert body["matter_type"] == "ragging"
        assert body["last_action_type"] == "registered"
        assert body["institution_ids"] == [str(world["institution"])]
    finally:
        await _cleanup_user(u.user_id)


async def test_register_case_rejects_unknown_matter_type(world):
    u = await _login_as("registry_operator")
    try:
        resp = u.client.post(
            "/api/v1/cases",
            json=_register_body(world, world["bureau_a"], matter_type="not_a_real_type"),
            headers=u.headers,
        )
        assert resp.status_code == 422
    finally:
        await _cleanup_user(u.user_id)


async def test_register_case_requires_at_least_one_institution(world):
    u = await _login_as("registry_operator")
    try:
        body = _register_body(world, world["bureau_a"])
        body["institution_ids"] = []
        resp = u.client.post("/api/v1/cases", json=body, headers=u.headers)
        assert resp.status_code == 422
    finally:
        await _cleanup_user(u.user_id)


async def test_duplicate_check_surfaces_other_open_case_same_institution(world):
    u = await _login_as("registry_operator")
    try:
        r1 = u.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=u.headers)
        case_id = r1.json()["id"]

        dup = u.client.get(
            "/api/v1/cases/duplicate-check", params={"institution_id": str(world["institution"])}, headers=u.headers
        )
        assert dup.status_code == 200
        assert any(c["id"] == case_id for c in dup.json())
    finally:
        await _cleanup_user(u.user_id)


async def test_duplicate_check_allowed_for_own_bureau_head(world):
    """Regression: duplicate_check's can() call originally omitted
    bureau_ids entirely, so the OWN_BUREAU intersection check
    (actor_bureau_ids & resource_bureau_ids) was always empty and every
    bureau_head/case_officer got 403 on this pre-submission check —
    never caught before because the only prior duplicate-check test
    used registry_operator, whose case:register is Scope.ALL."""
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        resp = u.client.get(
            "/api/v1/cases/duplicate-check",
            params={"institution_id": str(world["institution"])},
            headers=u.headers,
        )
        assert resp.status_code == 200
    finally:
        await _cleanup_user(u.user_id)


async def test_bureau_head_can_list_users_in_own_bureau(world):
    """Regression: list_users's can() call omitted resource_bureau_ids,
    so OWN_BUREAU-scoped roles (bureau_head, case_officer, ...) always
    got 403 from GET /users, regardless of real bureau membership —
    this silently broke the case-detail screen's officer-assignment
    dropdown for every bureau_head in the real app."""
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    officer = await _login_as("case_officer", bureau_id=world["bureau_a"])
    try:
        resp = head.client.get("/api/v1/users", headers=head.headers)
        assert resp.status_code == 200
        assert any(row["id"] == str(officer.user_id) for row in resp.json())
    finally:
        await _cleanup_user(head.user_id)
        await _cleanup_user(officer.user_id)


async def test_regional_officer_cannot_register(world):
    u = await _login_as("regional_officer")
    try:
        resp = u.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=u.headers)
        assert resp.status_code == 403
    finally:
        await _cleanup_user(u.user_id)


async def test_case_list_is_t1_visible_to_every_role(world):
    reg = await _login_as("registry_operator")
    try:
        r1 = reg.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=reg.headers)
        case_id = r1.json()["id"]

        viewer = await _login_as("regional_officer")
        try:
            listing = viewer.client.get("/api/v1/cases", headers=viewer.headers)
            assert listing.status_code == 200
            assert any(c["id"] == case_id for c in listing.json()["items"])
        finally:
            await _cleanup_user(viewer.user_id)
    finally:
        await _cleanup_user(reg.user_id)


async def test_only_handling_bureau_can_read_case_events(world):
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        r1 = head.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers)
        case_id = r1.json()["id"]

        own = head.client.get(f"/api/v1/cases/{case_id}/events", headers=head.headers)
        assert own.status_code == 200
        assert own.json()[0]["event_type"] == "registered"

        other = await _login_as("case_officer", bureau_id=world["bureau_b"])
        try:
            denied = other.client.get(f"/api/v1/cases/{case_id}/events", headers=other.headers)
            assert denied.status_code == 403
        finally:
            await _cleanup_user(other.user_id)

        ca = await _login_as("competent_authority")
        try:
            ca_view = ca.client.get(f"/api/v1/cases/{case_id}/events", headers=ca.headers)
            assert ca_view.status_code == 200
        finally:
            await _cleanup_user(ca.user_id)
    finally:
        await _cleanup_user(head.user_id)


async def test_assign_moves_pending_to_under_process(world):
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    officer = await _login_as("case_officer", bureau_id=world["bureau_a"])
    try:
        r1 = head.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers)
        case_id = r1.json()["id"]

        resp = head.client.post(
            f"/api/v1/cases/{case_id}/assign", json={"officer_id": str(officer.user_id)}, headers=head.headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "under_process"
        assert resp.json()["assigned_officer_id"] == str(officer.user_id)
    finally:
        await _cleanup_user(head.user_id)
        await _cleanup_user(officer.user_id)


async def test_remark_is_recorded_as_an_event_with_the_actor(world):
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        r1 = head.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers)
        case_id = r1.json()["id"]

        resp = head.client.post(
            f"/api/v1/cases/{case_id}/remark",
            json={"remark": "Awaiting inspection report", "next_action_required": "Site visit"},
            headers=head.headers,
        )
        assert resp.status_code == 200
        assert resp.json()["next_action_required"] == "Site visit"

        events = head.client.get(f"/api/v1/cases/{case_id}/events", headers=head.headers).json()
        remark_events = [e for e in events if e["event_type"] == "remark_added"]
        assert remark_events[0]["remark"] == "Awaiting inspection report"
        assert remark_events[0]["actor_role"] == "bureau_head"
    finally:
        await _cleanup_user(head.user_id)


async def test_transfer_propose_accept_moves_bureau_and_clears_officer(world):
    head_a = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    head_b = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    officer = await _login_as("case_officer", bureau_id=world["bureau_a"])
    try:
        r1 = head_a.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head_a.headers)
        case_id = r1.json()["id"]
        head_a.client.post(
            f"/api/v1/cases/{case_id}/assign", json={"officer_id": str(officer.user_id)}, headers=head_a.headers
        )

        propose = head_a.client.post(
            f"/api/v1/cases/{case_id}/transfer/propose",
            json={"to_bureau_id": str(world["bureau_b"]), "reason": "Better jurisdiction fit"},
            headers=head_a.headers,
        )
        assert propose.status_code == 201
        transfer_id = propose.json()["transfer_id"]

        mid = head_a.client.get(f"/api/v1/cases/{case_id}", headers=head_a.headers).json()
        assert mid["status"] == "transferred"

        # Bureau A (the proposer) cannot accept its own transfer.
        wrong_accept = head_a.client.post(
            f"/api/v1/cases/{case_id}/transfer/{transfer_id}/accept", headers=head_a.headers
        )
        assert wrong_accept.status_code == 403

        accept = head_b.client.post(
            f"/api/v1/cases/{case_id}/transfer/{transfer_id}/accept", headers=head_b.headers
        )
        assert accept.status_code == 200
        assert accept.json()["status"] == "under_process"
        assert accept.json()["assigned_bureau_id"] == str(world["bureau_b"])
        assert accept.json()["assigned_officer_id"] is None
    finally:
        await _cleanup_user(head_a.user_id)
        await _cleanup_user(head_b.user_id)
        await _cleanup_user(officer.user_id)


async def test_transfer_reject_keeps_case_with_proposing_bureau(world):
    head_a = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    head_b = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        r1 = head_a.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head_a.headers)
        case_id = r1.json()["id"]
        propose = head_a.client.post(
            f"/api/v1/cases/{case_id}/transfer/propose",
            json={"to_bureau_id": str(world["bureau_b"]), "reason": "Wrong bureau"},
            headers=head_a.headers,
        )
        transfer_id = propose.json()["transfer_id"]

        reject = head_b.client.post(f"/api/v1/cases/{case_id}/transfer/{transfer_id}/reject", headers=head_b.headers)
        assert reject.status_code == 200
        assert reject.json()["status"] == "under_process"
        assert reject.json()["assigned_bureau_id"] == str(world["bureau_a"])
    finally:
        await _cleanup_user(head_a.user_id)
        await _cleanup_user(head_b.user_id)


async def test_escalate_dispose_reopen_round_trip(world):
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        r1 = head.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers)
        case_id = r1.json()["id"]

        esc = head.client.post(f"/api/v1/cases/{case_id}/escalate", headers=head.headers)
        assert esc.json()["status"] == "escalated"

        disp = head.client.post(
            f"/api/v1/cases/{case_id}/dispose",
            json={"disposal_type": "resolved", "remark": "Institution complied"},
            headers=head.headers,
        )
        assert disp.status_code == 200
        assert disp.json()["status"] == "disposed"
        assert disp.json()["disposed_at"] is not None

        reopen = head.client.post(f"/api/v1/cases/{case_id}/reopen", headers=head.headers)
        assert reopen.status_code == 200
        assert reopen.json()["status"] == "under_process"
        assert reopen.json()["disposed_at"] is None

        cannot_reopen_twice = head.client.post(f"/api/v1/cases/{case_id}/reopen", headers=head.headers)
        assert cannot_reopen_twice.status_code == 409
    finally:
        await _cleanup_user(head.user_id)


async def test_counters_reconcile_against_raw_row_counts(world):
    """Section 6.5/16: the reconciliation check IS comparing the
    endpoint's answer to a raw recomputation — if they ever disagree,
    this is the drift Section 6.5 calls out."""
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        head.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers)

        resp = head.client.get("/api/v1/cases/counters", headers=head.headers)
        assert resp.status_code == 200
        counters = resp.json()

        async with OwnerSession() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
            raw_total = (await session.execute(text("SELECT count(*) FROM cases"))).scalar_one()
            raw_pending = (
                await session.execute(text("SELECT count(*) FROM cases WHERE status = 'pending'"))
            ).scalar_one()

        assert counters["total"] == raw_total
        assert counters["pending"] == raw_pending
    finally:
        await _cleanup_user(head.user_id)


async def test_projection_replay_matches_live_state_after_a_full_workflow(world):
    """The actual Phase 3 gate item: rebuild the projection purely from
    case_events and compare to the live `cases` row — using the real
    rebuild_projection module, not a reimplementation of it."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import rebuild_projection

    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    officer = await _login_as("case_officer", bureau_id=world["bureau_a"])
    try:
        r1 = head.client.post("/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers)
        case_id = r1.json()["id"]
        head.client.post(
            f"/api/v1/cases/{case_id}/assign", json={"officer_id": str(officer.user_id)}, headers=head.headers
        )
        head.client.post(f"/api/v1/cases/{case_id}/remark", json={"remark": "progress"}, headers=head.headers)
        head.client.post(f"/api/v1/cases/{case_id}/escalate", headers=head.headers)
        head.client.post(
            f"/api/v1/cases/{case_id}/dispose",
            json={"disposal_type": "resolved", "remark": "done"},
            headers=head.headers,
        )

        async with OwnerSession() as session, session.begin():
            # 'system', matching rebuild_projection.py's own role choice
            # (super_admin has no case_events read access by design).
            await session.execute(text("SELECT set_config('app.role', 'system', true)"))
            from sqlalchemy import select

            from app.models import Case

            case = (await session.execute(select(Case).where(Case.id == uuid.UUID(case_id)))).scalar_one()
            mismatches = await rebuild_projection.check_case(session, case)

        assert mismatches == [], f"projection drift: {mismatches}"
    finally:
        await _cleanup_user(head.user_id)
        await _cleanup_user(officer.user_id)
