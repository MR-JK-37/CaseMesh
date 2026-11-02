"""Phase 4 gate (Section 16): R4, R5, R6, R12 — same-institution overlap
detection incl. different-wording and different-institution negatives,
grouped queue, confirm/dismiss/coordinate/decide, banner-backing
endpoints. Drives real HTTP requests through the real FastAPI app and
Postgres, same discipline as test_cases_api.py (reused here via import,
not duplicated)."""

import uuid

import pytest

from app.models import Bureau, Institution

from .db_helpers import OwnerSession
from .test_cases_api import (  # noqa: F401
    _cleanup_user,
    _login_as,
    _register_body,
    _reset_rate_limit_buckets,
    world,
)


async def _register(session_user, world, bureau_id, **overrides):
    resp = session_user.client.post("/api/v1/cases", json=_register_body(world, bureau_id, **overrides), headers=session_user.headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def second_institution():
    inst_id = uuid.uuid4()
    async with OwnerSession() as session, session.begin():
        session.add(
            Institution(
                id=inst_id,
                permanent_id=f"1-{uuid.uuid4().int % 900000000 + 100000000}",
                name="Overlap Test Second Institute",
                status="active",
                data_origin="user_entered",
                source_name="test fixture",
            )
        )
    yield inst_id


async def test_same_institution_different_wording_produces_overlap_r4(world):
    """R4: same institution, different bureaus, different free-text
    descriptions, no shared reference — still flagged."""
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        case_a = await _register(
            rb, world, world["bureau_a"], description="Student alleges faculty misconduct during practicals"
        )
        case_b = await _register(
            pgrc, world, world["bureau_b"], description="Complaint about professor behaviour in laboratory sessions"
        )

        resp = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers)
        assert resp.status_code == 200
        candidates = resp.json()
        assert any(c["case_b_id"] == case_b["id"] or c["case_a_id"] == case_b["id"] for c in candidates)
        match = next(c for c in candidates if case_b["id"] in (c["case_a_id"], c["case_b_id"]))
        assert match["level"] in ("potential", "high")
        assert any(r["code"] == "different_bureau" for r in match["reasons"])
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)


async def test_different_institution_cases_are_never_paired_r4_negative(world, second_institution):
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        case_a = await _register(rb, world, world["bureau_a"])
        body = _register_body(world, world["bureau_a"])
        body["institution_ids"] = [str(second_institution)]
        resp = rb.client.post("/api/v1/cases", json=body, headers=rb.headers)
        assert resp.status_code == 201
        case_b = resp.json()

        overlaps = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers).json()
        assert not any(case_b["id"] in (c["case_a_id"], c["case_b_id"]) for c in overlaps)
    finally:
        await _cleanup_user(rb.user_id)


async def test_shared_reference_pair_appears_in_grouped_queue_r5(world):
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        await _register(rb, world, world["bureau_a"], external_refs=["LTR/2026/555"])
        await _register(pgrc, world, world["bureau_b"], external_refs=["LTR/2026/555"])

        groups = rb.client.get("/api/v1/overlap/groups", headers=rb.headers).json()
        group = next(g for g in groups if g["institution_id"] == str(world["institution"]))
        assert group["max_level"] == "high"
        assert any(c["level"] == "high" for c in group["candidates"])
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)


async def test_bureau_head_confirm_and_link_r6(world):
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        case_a = await _register(rb, world, world["bureau_a"], external_refs=["LTR/2026/777"])
        await _register(pgrc, world, world["bureau_b"], external_refs=["LTR/2026/777"])
        candidate = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers).json()[0]

        resp = rb.client.post(
            f"/api/v1/overlap/candidates/{candidate['id']}/confirm",
            json={"relationship_type": "duplicate"},
            headers=rb.headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "confirmed"
        assert resp.json()["relationship_type"] == "duplicate"
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)


async def test_dismiss_requires_a_reason(world):
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        case_a = await _register(rb, world, world["bureau_a"], external_refs=["LTR/2026/888"])
        await _register(pgrc, world, world["bureau_b"], external_refs=["LTR/2026/888"])
        candidate = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers).json()[0]

        empty = rb.client.post(
            f"/api/v1/overlap/candidates/{candidate['id']}/dismiss", json={"reason": "  "}, headers=rb.headers
        )
        assert empty.status_code == 422

        ok = rb.client.post(
            f"/api/v1/overlap/candidates/{candidate['id']}/dismiss",
            json={"reason": "Different institutions mentioned in follow-up, not a real duplicate"},
            headers=rb.headers,
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "dismissed"
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)


async def test_outside_bureau_cannot_confirm_r6_security(world):
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    outsider_bureau = uuid.uuid4()
    async with OwnerSession() as session, session.begin():
        session.add(Bureau(id=outsider_bureau, name="Overlap Test Outsider Bureau", kind="bureau"))
    outsider = await _login_as("bureau_head", bureau_id=outsider_bureau)
    try:
        case_a = await _register(rb, world, world["bureau_a"], external_refs=["LTR/2026/999"])
        await _register(pgrc, world, world["bureau_b"], external_refs=["LTR/2026/999"])
        candidate = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers).json()[0]

        resp = outsider.client.post(
            f"/api/v1/overlap/candidates/{candidate['id']}/confirm",
            json={"relationship_type": "duplicate"},
            headers=outsider.headers,
        )
        assert resp.status_code == 403
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)
        await _cleanup_user(outsider.user_id)


async def test_coordination_thread_and_decision_require_reason_r12(world):
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        case_a = await _register(rb, world, world["bureau_a"], external_refs=["LTR/2026/111"])
        await _register(pgrc, world, world["bureau_b"], external_refs=["LTR/2026/111"])
        candidate = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers).json()[0]

        thread = rb.client.post(
            f"/api/v1/overlap/candidates/{candidate['id']}/coordinate",
            json={"lead_bureau_id": str(world["bureau_a"])},
            headers=rb.headers,
        )
        assert thread.status_code == 201, thread.text
        thread_id = thread.json()["id"]

        msg = pgrc.client.post(
            f"/api/v1/overlap/threads/{thread_id}/messages",
            json={"body": "PGRC already issued a show-cause notice on this institution."},
            headers=pgrc.headers,
        )
        assert msg.status_code == 201, msg.text

        no_reason = rb.client.post(
            f"/api/v1/overlap/threads/{thread_id}/decision",
            json={"decision_type": "proceed_in_parallel", "reason": ""},
            headers=rb.headers,
        )
        assert no_reason.status_code == 422

        decided = rb.client.post(
            f"/api/v1/overlap/threads/{thread_id}/decision",
            json={
                "decision_type": "proceed_in_parallel",
                "reason": "Different jurisdictional basis (RB regulatory vs PGRC grievance) — proceeding separately.",
            },
            headers=rb.headers,
        )
        assert decided.status_code == 201, decided.text
        assert decided.json()["decision_type"] == "proceed_in_parallel"
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)


async def test_thread_messages_hidden_from_uninvolved_bureau(world):
    """T2-equivalent boundary for coordination content (Section 4.3),
    mirroring Phase 3's case_events bureau restriction."""
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    outsider_bureau = uuid.uuid4()
    async with OwnerSession() as session, session.begin():
        session.add(Bureau(id=outsider_bureau, name="Overlap Test Outsider Bureau 2", kind="bureau"))
    outsider = await _login_as("bureau_head", bureau_id=outsider_bureau)
    try:
        case_a = await _register(rb, world, world["bureau_a"], external_refs=["LTR/2026/222"])
        await _register(pgrc, world, world["bureau_b"], external_refs=["LTR/2026/222"])
        candidate = rb.client.get(f"/api/v1/cases/{case_a['id']}/overlaps", headers=rb.headers).json()[0]
        thread = rb.client.post(
            f"/api/v1/overlap/candidates/{candidate['id']}/coordinate", json={}, headers=rb.headers
        ).json()

        resp = outsider.client.get(f"/api/v1/overlap/threads/{thread['id']}/messages", headers=outsider.headers)
        assert resp.status_code == 403
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)
        await _cleanup_user(outsider.user_id)
