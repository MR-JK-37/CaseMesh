"""Phase 5 gate (Section 16): R10 — alert catalogue fires once per
threshold; SLA policy lookup/business-day due-date computation against
real seeded data.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.models import SlaPolicy
from app.services.alerts import raise_alert
from app.services.sla import compute_sla_status, fetch_policy, sla_facts_for_case

from .db_helpers import OwnerSession
from .test_cases_api import _cleanup_user, _login_as, _reset_rate_limit_buckets, world  # noqa: F401


@pytest.fixture
async def cpgrams_policy():
    policy_id = uuid.uuid4()
    async with OwnerSession() as session, session.begin():
        session.add(
            SlaPolicy(
                id=policy_id,
                source_channel="cpgrams",
                matter_type=None,
                priority="standard",
                days=21,
                warn_at=[5, 2],
                version=1,
                source_name="test fixture",
            )
        )
    yield policy_id


async def test_raise_alert_fires_once_per_dedup_key_r10():
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        key = f"test-dedup-{uuid.uuid4()}"
        first = await raise_alert(
            session,
            code="CASE_STALE",
            severity="warning",
            resource_type="case",
            resource_id=None,
            message="first",
            dedup_key=key,
        )
        second = await raise_alert(
            session,
            code="CASE_STALE",
            severity="warning",
            resource_type="case",
            resource_id=None,
            message="second — should be suppressed",
            dedup_key=key,
        )
        assert first is not None
        assert second is None


async def test_raise_alert_different_dedup_keys_both_fire():
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        a = await raise_alert(
            session,
            code="SLA_APPROACHING",
            severity="warning",
            resource_type="case",
            resource_id=None,
            message="a",
            dedup_key=f"test-{uuid.uuid4()}",
        )
        b = await raise_alert(
            session,
            code="SLA_APPROACHING",
            severity="warning",
            resource_type="case",
            resource_id=None,
            message="b",
            dedup_key=f"test-{uuid.uuid4()}",
        )
        assert a is not None
        assert b is not None
        assert a.id != b.id


async def test_raise_alert_rejects_unknown_code():
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        with pytest.raises(ValueError):
            await raise_alert(
                session,
                code="NOT_A_REAL_CODE",
                severity="info",
                resource_type="case",
                resource_id=None,
                message="x",
                dedup_key=f"test-{uuid.uuid4()}",
            )


async def test_fetch_policy_wildcard_matter_type(cpgrams_policy):
    async with OwnerSession() as session, session.begin():
        policy = await fetch_policy(session, source_channel="cpgrams", matter_type="ragging", priority="standard")
        assert policy is not None
        assert policy.days == 21


async def test_fetch_policy_absent_for_unseeded_combination(cpgrams_policy):
    async with OwnerSession() as session, session.begin():
        policy = await fetch_policy(session, source_channel="letter", matter_type="ragging", priority="standard")
        assert policy is None


async def test_sla_facts_not_set_without_a_policy():
    async with OwnerSession() as session, session.begin():
        facts = await sla_facts_for_case(
            session,
            source_channel="letter",
            matter_type="ragging",
            priority="standard",
            received_at=dt.datetime.now(dt.UTC),
        )
        assert facts.status == "not_set"
        assert facts.due_at is None


async def test_sla_facts_due_at_skips_weekends(cpgrams_policy):
    async with OwnerSession() as session, session.begin():
        received = dt.datetime(2026, 11, 2, tzinfo=dt.UTC)  # a Monday
        facts = await sla_facts_for_case(
            session,
            source_channel="cpgrams",
            matter_type=None,
            priority="standard",
            received_at=received,
            holidays=frozenset(),
        )
        assert facts.due_at is not None
        assert facts.due_at.weekday() < 5  # never lands on a weekend


async def test_compute_sla_status_breached_after_due_date():
    due = dt.date(2026, 1, 1)
    status = compute_sla_status(
        dt.datetime(2025, 12, 1, tzinfo=dt.UTC),
        due,
        now=dt.datetime(2026, 1, 5, tzinfo=dt.UTC),
        holidays=frozenset(),
        warn_at=[5, 2],
    )
    assert status == "breached"


async def test_compute_sla_status_approaching_within_warn_window():
    due = dt.date(2026, 11, 10)  # a Tuesday
    status = compute_sla_status(
        dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
        due,
        now=dt.datetime(2026, 11, 9, tzinfo=dt.UTC),  # 1 business day out
        holidays=frozenset(),
        warn_at=[5, 2],
    )
    assert status == "approaching"


async def test_compute_sla_status_on_track_outside_warn_window():
    due = dt.date(2026, 12, 1)
    status = compute_sla_status(
        dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
        due,
        now=dt.datetime(2026, 10, 2, tzinfo=dt.UTC),
        holidays=frozenset(),
        warn_at=[5, 2],
    )
    assert status == "on_track"


async def test_register_case_without_matching_policy_raises_sla_policy_missing(world):
    """Section 7.2: no policy for (letter, ragging, standard) is seeded
    by the `world` fixture's bureau/institution setup — registering such
    a case must raise SLA_POLICY_MISSING (deduped per gap, not per
    case) and the case itself must report sla_status="not_set"."""
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        resp = u.client.post(
            "/api/v1/cases",
            json={
                "institution_ids": [str(world["institution"])],
                "matter_type": "ragging",
                "source_channel": "letter",
                "priority": "standard",
                "assigned_bureau_id": str(world["bureau_a"]),
            },
            headers=u.headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["sla_status"] == "not_set"
        assert body["due_at"] is None

        async with OwnerSession() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', 'system', true)"))
            row = (
                await session.execute(
                    text(
                        "SELECT 1 FROM alerts WHERE dedup_key = :key"
                    ),
                    {"key": "SLA_POLICY_MISSING:letter:ragging:standard"},
                )
            ).first()
            assert row is not None
    finally:
        await _cleanup_user(u.user_id)


async def test_bureau_head_can_ack_overlap_alert_for_own_bureau_cases(world):
    """Regression: `ack_alert`'s bureau resolution originally only
    handled `resource_type=="case"`, so an OVERLAP_DETECTED/
    HIGH_CONFIDENCE alert (resource_type="overlap_candidate") always
    403'd for every bureau_head, even for their own bureau's cases —
    found live in the browser, not anticipated. Fixed by resolving the
    candidate's own two member cases' bureaus, the same union
    app/routers/overlap.py's confirm/dismiss/coordinate/decide actions
    already use for this exact resource."""
    rb = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    pgrc = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        case_a = rb.client.post(
            "/api/v1/cases",
            json={
                "institution_ids": [str(world["institution"])],
                "matter_type": "ragging",
                "source_channel": "letter",
                "assigned_bureau_id": str(world["bureau_a"]),
                "external_refs": ["LTR/ACK/001"],
            },
            headers=rb.headers,
        ).json()
        pgrc.client.post(
            "/api/v1/cases",
            json={
                "institution_ids": [str(world["institution"])],
                "matter_type": "ragging",
                "source_channel": "letter",
                "assigned_bureau_id": str(world["bureau_b"]),
                "external_refs": ["LTR/ACK/001"],
            },
            headers=pgrc.headers,
        )

        alerts = rb.client.get("/api/v1/alerts", headers=rb.headers).json()
        target = next(a for a in alerts if a["resource_type"] == "overlap_candidate" and case_a["case_number"] in a["message"])

        ack = rb.client.post(f"/api/v1/alerts/{target['id']}/ack", headers=rb.headers)
        assert ack.status_code == 200, ack.text
        assert ack.json()["acked_at"] is not None
    finally:
        await _cleanup_user(rb.user_id)
        await _cleanup_user(pgrc.user_id)


async def test_holiday_table_is_queryable_and_seeded_rows_are_real_dates():
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        rows = (await session.execute(text("SELECT holiday_date, name FROM holidays LIMIT 5"))).all()
        # Not asserting a specific count (seeding is a separate, optional
        # script run) — only that whatever exists is a real typed date
        # with a non-empty name, not a placeholder.
        for holiday_date, name in rows:
            assert isinstance(holiday_date, dt.date)
            assert name
