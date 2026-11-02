"""Integration tests against the real Postgres + the real FastAPI app.
Drives the actual upload -> preview -> commit -> verify flow (Section
1.4: nothing is written to `institutions` until a human commits the
preview, and new rows start `pending_review` until a separate verify
step) rather than calling the service functions directly."""

import io
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password
from app.core.valkey import get_valkey_client
from app.main import app
from app.models import TOTP_REQUIRED_ROLES, User

from .db_helpers import OwnerSession

client = TestClient(app)
PASSWORD = "Correct-Horse-Battery-Staple-9"


async def _login_as(role: str) -> tuple[uuid.UUID, dict]:
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
    body = {"email": email, "password": PASSWORD}
    if totp_secret:
        body["totp_code"] = pyotp.TOTP(totp_secret).now()
    resp = client.post("/api/v1/auth/login", json=body)
    assert resp.status_code == 200, resp.text
    csrf = resp.cookies["icm_csrf"]
    return user_id, {"X-CSRF-Token": csrf}


async def _cleanup_user(user_id: uuid.UUID) -> None:
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        # Covers orphaned import_jobs/source_documents too (e.g. a job
        # whose only row errored, so no institution was ever created to
        # anchor cleanup to) — this test file's own `uploaded_by` FK
        # chain, not just the users row itself.
        job_ids = (
            await session.execute(
                text(
                    "SELECT id FROM import_jobs WHERE source_document_id IN "
                    "(SELECT id FROM source_documents WHERE uploaded_by = :id)"
                ),
                {"id": user_id},
            )
        ).scalars().all()
        await session.execute(text("DELETE FROM import_job_rows WHERE import_job_id = ANY(:ids)"), {"ids": job_ids})
        await session.execute(
            text("UPDATE institutions SET import_job_id = NULL WHERE import_job_id = ANY(:ids)"),
            {"ids": job_ids},
        )
        await session.execute(text("DELETE FROM import_jobs WHERE id = ANY(:ids)"), {"ids": job_ids})
        await session.execute(text("DELETE FROM source_documents WHERE uploaded_by = :id"), {"id": user_id})
        await session.execute(
            text("DELETE FROM refresh_token_families WHERE user_id = :id"), {"id": user_id}
        )
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


async def _cleanup_institution(permanent_id: str) -> None:
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        inst_ids = (
            await session.execute(
                text("SELECT id FROM institutions WHERE permanent_id = :p"), {"p": permanent_id}
            )
        ).scalars().all()
        job_ids = (
            await session.execute(
                text(
                    "SELECT import_job_id FROM institutions WHERE permanent_id = :p "
                    "UNION SELECT import_job_id FROM import_job_rows WHERE institution_id = ANY(:iids)"
                ),
                {"p": permanent_id, "iids": inst_ids},
            )
        ).scalars().all()
        # FK order: import_job_rows (by institution_id, covers every job
        # that ever touched this institution, not just its current one)
        # -> institutions -> import_jobs -> source_documents.
        await session.execute(
            text("DELETE FROM import_job_rows WHERE institution_id = ANY(:iids)"), {"iids": inst_ids}
        )
        await session.execute(text("DELETE FROM institutions WHERE permanent_id = :p"), {"p": permanent_id})
        doc_ids = (
            await session.execute(
                text("SELECT source_document_id FROM import_jobs WHERE id = ANY(:ids)"), {"ids": job_ids}
            )
        ).scalars().all()
        await session.execute(text("DELETE FROM import_jobs WHERE id = ANY(:ids)"), {"ids": job_ids})
        await session.execute(
            text("DELETE FROM source_documents WHERE id = ANY(:ids)"), {"ids": doc_ids}
        )


@pytest.fixture(autouse=True)
async def _reset_rate_limit_buckets():
    yield
    r = get_valkey_client()
    async for key in r.scan_iter("ratelimit:login:*"):
        await r.delete(key)


def _csv_file(permanent_id: str, name: str = "Test Institute"):
    content = f"permanent_id,name,state\n{permanent_id},{name},Test State\n".encode()
    return {"file": ("institutions.csv", io.BytesIO(content), "text/csv")}


async def test_preview_does_not_write_to_institutions():
    user_id, headers = await _login_as("super_admin")
    permanent_id = "1-900000001"
    try:
        resp = client.post(
            "/api/v1/imports",
            files=_csv_file(permanent_id),
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["rows"][0]["action"] == "create"
        assert body["row_count"] == 1

        # Not written yet.
        listing = client.get("/api/v1/institutions", headers=headers)
        assert all(i["permanent_id"] != permanent_id for i in listing.json())
    finally:
        await _cleanup_institution(permanent_id)
        await _cleanup_user(user_id)


async def test_commit_creates_a_pending_review_institution():
    user_id, headers = await _login_as("super_admin")
    permanent_id = "1-900000002"
    try:
        preview = client.post(
            "/api/v1/imports",
            files=_csv_file(permanent_id),
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        job_id = preview.json()["id"]

        commit = client.post(f"/api/v1/imports/{job_id}/commit", headers=headers)
        assert commit.status_code == 200
        assert commit.json()["created"] == 1

        listing = client.get("/api/v1/institutions", headers=headers)
        row = next(i for i in listing.json() if i["permanent_id"] == permanent_id)
        assert row["status"] == "pending_review"
        assert row["data_origin"] == "user_entered"
        assert row["source_name"] == "test sandbox fixture"
    finally:
        await _cleanup_institution(permanent_id)
        await _cleanup_user(user_id)


async def test_verify_activates_and_records_who():
    user_id, headers = await _login_as("super_admin")
    permanent_id = "1-900000003"
    try:
        preview = client.post(
            "/api/v1/imports",
            files=_csv_file(permanent_id),
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        job_id = preview.json()["id"]
        client.post(f"/api/v1/imports/{job_id}/commit", headers=headers)

        listing = client.get("/api/v1/institutions", headers=headers)
        inst_id = next(i["id"] for i in listing.json() if i["permanent_id"] == permanent_id)

        verify = client.post(f"/api/v1/institutions/{inst_id}/verify", headers=headers)
        assert verify.status_code == 200
        assert verify.json()["status"] == "active"
        assert verify.json()["verified_at"] is not None
    finally:
        await _cleanup_institution(permanent_id)
        await _cleanup_user(user_id)


async def test_reimport_of_same_permanent_id_is_an_update_not_a_duplicate():
    user_id, headers = await _login_as("super_admin")
    permanent_id = "1-900000004"
    try:
        p1 = client.post(
            "/api/v1/imports",
            files=_csv_file(permanent_id, "Original Name"),
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        client.post(f"/api/v1/imports/{p1.json()['id']}/commit", headers=headers)

        p2 = client.post(
            "/api/v1/imports",
            files=_csv_file(permanent_id, "Updated Name"),
            data={"source_name": "test sandbox fixture, revision"},
            headers=headers,
        )
        assert p2.json()["rows"][0]["action"] == "update"
        assert p2.json()["rows"][0]["diff"]["name"] == {"old": "Original Name", "new": "Updated Name"}

        commit2 = client.post(f"/api/v1/imports/{p2.json()['id']}/commit", headers=headers)
        assert commit2.json()["updated"] == 1

        listing = client.get("/api/v1/institutions", headers=headers)
        matches = [i for i in listing.json() if i["permanent_id"] == permanent_id]
        assert len(matches) == 1
        assert matches[0]["name"] == "Updated Name"
    finally:
        await _cleanup_institution(permanent_id)
        await _cleanup_user(user_id)


async def test_invalid_row_is_reported_as_an_error_not_silently_dropped():
    user_id, headers = await _login_as("super_admin")
    try:
        content = b"permanent_id,name\nnot-valid,Bad Row Institute\n"
        resp = client.post(
            "/api/v1/imports",
            files={"file": ("bad.csv", io.BytesIO(content), "text/csv")},
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        body = resp.json()
        assert body["error_count"] == 1
        assert body["rows"][0]["action"] == "error"
        assert body["rows"][0]["errors"]
    finally:
        await _cleanup_user(user_id)


async def test_non_import_role_cannot_upload():
    user_id, headers = await _login_as("case_officer")
    try:
        resp = client.post(
            "/api/v1/imports",
            files=_csv_file("1-900000005"),
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        assert resp.status_code == 403
    finally:
        await _cleanup_user(user_id)


async def test_institution_case_history_is_honestly_empty():
    user_id, headers = await _login_as("super_admin")
    permanent_id = "1-900000006"
    try:
        preview = client.post(
            "/api/v1/imports",
            files=_csv_file(permanent_id),
            data={"source_name": "test sandbox fixture"},
            headers=headers,
        )
        job_id = preview.json()["id"]
        client.post(f"/api/v1/imports/{job_id}/commit", headers=headers)
        listing = client.get("/api/v1/institutions", headers=headers)
        inst_id = next(i["id"] for i in listing.json() if i["permanent_id"] == permanent_id)

        cases = client.get(f"/api/v1/institutions/{inst_id}/cases", headers=headers)
        assert cases.status_code == 200
        assert cases.json()["cases"] == []
    finally:
        await _cleanup_institution(permanent_id)
        await _cleanup_user(user_id)


async def test_system_info_reports_test_sandbox_mode_unauthenticated():
    resp = client.get("/api/v1/system/info")
    assert resp.status_code == 200
    assert resp.json()["tenant_mode"] == "test_sandbox"
