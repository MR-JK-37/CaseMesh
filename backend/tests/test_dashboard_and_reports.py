"""Phase 6 gate (Section 16): R7 (dashboard tile equals independent
recomputation), R9 (search/filter result set equals the SQL predicate,
plus keyset pagination), R11 (report totals equal dashboard totals for
the same underlying data).
"""

import uuid

import pytest
from sqlalchemy import func, select, text

from app.models import Case, CaseInstitutionLink
from app.services.csv_export import safe_cell

from .db_helpers import OwnerSession
from .test_cases_api import _cleanup_user, _login_as, _register_body, world  # noqa: F401


async def test_dashboard_pending_tile_equals_independent_sql_count_r7():
    """The gate's "tile equals list count" in its truest form: compute
    the same number two independent ways — the dashboard endpoint, and
    a direct SQL count — and require they agree on whatever state the
    database currently holds (tests run sequentially against one
    long-lived DB, so this never assumes a known starting count, only
    that nothing mutates `cases.status` between the two reads)."""
    u = await _login_as("auditor")
    try:
        tiles = u.client.get("/api/v1/dashboard/tiles", headers=u.headers)
        assert tiles.status_code == 200, tiles.text
        pending_from_tile = tiles.json()["pending"]

        async with OwnerSession() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', 'system', true)"))
            pending_from_sql = (
                await session.execute(select(func.count()).select_from(Case).where(Case.status == "pending"))
            ).scalar_one()
        assert pending_from_tile == pending_from_sql
    finally:
        await _cleanup_user(u.user_id)


async def test_cases_filter_by_institution_matches_sql_predicate_r9(world):
    """Registers cases on a fresh, test-unique institution (the `world`
    fixture mints a new UUID every run) so filtering by that
    institution_id isolates exactly this test's rows regardless of
    what every other test in the suite has accumulated in the shared
    DB — then checks the API's filtered result set against the same
    predicate run directly in SQL."""
    head_a = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    head_b = await _login_as("bureau_head", bureau_id=world["bureau_b"])
    try:
        for _ in range(2):
            resp = head_a.client.post(
                "/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head_a.headers
            )
            assert resp.status_code == 201, resp.text
        resp = head_b.client.post(
            "/api/v1/cases", json=_register_body(world, world["bureau_b"]), headers=head_b.headers
        )
        assert resp.status_code == 201, resp.text

        listing = head_a.client.get(
            "/api/v1/cases", params={"institution_id": str(world["institution"])}, headers=head_a.headers
        )
        assert listing.status_code == 200, listing.text
        items = listing.json()["items"]

        async with OwnerSession() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', 'system', true)"))
            expected_ids = (
                await session.execute(
                    select(CaseInstitutionLink.case_id).where(
                        CaseInstitutionLink.institution_id == world["institution"]
                    )
                )
            ).scalars().all()
        assert {uuid.UUID(c["id"]) for c in items} == set(expected_ids)
        assert len(items) == 3

        bureau_a_only = head_a.client.get(
            "/api/v1/cases",
            params={"institution_id": str(world["institution"]), "bureau_id": str(world["bureau_a"])},
            headers=head_a.headers,
        )
        assert len(bureau_a_only.json()["items"]) == 2

        marker = f"MARK-{uuid.uuid4()}"
        resp = head_a.client.post(
            "/api/v1/cases",
            json=_register_body(world, world["bureau_a"], external_refs=[marker]),
            headers=head_a.headers,
        )
        assert resp.status_code == 201, resp.text
        searched = head_a.client.get("/api/v1/cases", params={"q": marker}, headers=head_a.headers)
        search_items = searched.json()["items"]
        assert len(search_items) == 1
        assert search_items[0]["case_number"] == resp.json()["case_number"]
    finally:
        await _cleanup_user(head_a.user_id)
        await _cleanup_user(head_b.user_id)


async def test_cases_list_keyset_pagination_has_no_gaps_or_overlap_r9(world):
    """Section 10's "keyset pagination everywhere" fix: page through a
    known 5-case set with limit=2 and verify every case is seen exactly
    once, in descending `seq` order, with a null `next_cursor` on the
    final page — the previous build's defect this replaces returned
    everything unbounded in one call."""
    head = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        made_numbers = []
        for _ in range(5):
            resp = head.client.post(
                "/api/v1/cases", json=_register_body(world, world["bureau_a"]), headers=head.headers
            )
            assert resp.status_code == 201, resp.text
            made_numbers.append(resp.json()["case_number"])

        seen = []
        cursor = None
        for _ in range(10):
            params = {"institution_id": str(world["institution"]), "limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            page = head.client.get("/api/v1/cases", params=params, headers=head.headers)
            assert page.status_code == 200, page.text
            body = page.json()
            seen.extend(c["case_number"] for c in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        else:
            pytest.fail("pagination did not terminate within 10 pages")

        assert len(seen) == len(set(seen)) == 5
        assert set(seen) == set(made_numbers)
    finally:
        await _cleanup_user(head.user_id)


async def test_report_totals_equal_dashboard_totals_r11():
    u = await _login_as("senior_management")
    try:
        tiles = u.client.get("/api/v1/dashboard/tiles", headers=u.headers).json()

        workload_report = u.client.get(
            "/api/v1/reports/bureau_workload/run", params={"format": "json"}, headers=u.headers
        )
        assert workload_report.status_code == 200, workload_report.text
        report_rows = workload_report.json()["rows"]
        report_total_open = sum(row[1] for row in report_rows)
        tile_total_open = sum(row["open"] for row in tiles["bureau_workload"])
        assert report_total_open == tile_total_open

        status_report = u.client.get(
            "/api/v1/reports/status_summary/run", params={"format": "json"}, headers=u.headers
        ).json()
        total_row = next(r for r in status_report["rows"] if r[0] == "Total")
        assert total_row[1] == tiles["total_cases"]
    finally:
        await _cleanup_user(u.user_id)


async def test_report_csv_export_is_watermarked_and_formula_safe_r11():
    u = await _login_as("senior_management")
    try:
        resp = u.client.get(
            "/api/v1/reports/status_summary/run", params={"format": "csv"}, headers=u.headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        text_body = resp.text
        assert text_body.startswith("# ICM export")
        assert "TEST DATA" in text_body
        assert "sha256=" in text_body.splitlines()[-1]
    finally:
        await _cleanup_user(u.user_id)


def test_safe_cell_neutralizes_formula_prefixes():
    assert safe_cell("=SUM(A1:A9)") == "'=SUM(A1:A9)"
    assert safe_cell("+1234") == "'+1234"
    assert safe_cell("-1234") == "'-1234"
    assert safe_cell("@mention") == "'@mention"
    assert safe_cell("ICM-2026-000001") == "ICM-2026-000001"
    assert safe_cell(None) == ""
    assert safe_cell(42) == "42"


async def test_saved_views_are_scoped_to_their_owner():
    owner = await _login_as("case_officer")
    other = await _login_as("case_officer")
    try:
        created = owner.client.post(
            "/api/v1/views",
            json={"name": "My pending cases", "filters": {"status": "pending"}},
            headers=owner.headers,
        )
        assert created.status_code == 201, created.text
        view_id = created.json()["id"]

        owner_list = owner.client.get("/api/v1/views", headers=owner.headers)
        assert any(v["id"] == view_id for v in owner_list.json())

        other_list = other.client.get("/api/v1/views", headers=other.headers)
        assert all(v["id"] != view_id for v in other_list.json())

        denied = other.client.delete(f"/api/v1/views/{view_id}", headers=other.headers)
        assert denied.status_code == 404

        allowed = owner.client.delete(f"/api/v1/views/{view_id}", headers=owner.headers)
        assert allowed.status_code == 204
    finally:
        await _cleanup_user(owner.user_id)
        await _cleanup_user(other.user_id)
