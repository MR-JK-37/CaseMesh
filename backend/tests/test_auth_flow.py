"""Integration tests against the real Postgres + the real FastAPI app
(docker compose up -d postgres valkey). Exercises the actual cookie-based
session (Section 7.4), lockout, TOTP, and refresh-token rotation/reuse
detection — not mocks of any of it."""

import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.valkey import get_valkey_client
from app.main import app
from app.models import User

from .db_helpers import OwnerSession

client = TestClient(app)

PASSWORD = "Correct-Horse-Battery-Staple-9"


async def _make_user(role: str, *, email: str | None = None) -> tuple[uuid.UUID, str]:
    user_id = uuid.uuid4()
    email = email or f"{role}-{user_id}@example.test"
    async with OwnerSession() as session, session.begin():
        # icm_owner is a non-superuser role subject to FORCE ROW LEVEL
        # SECURITY like anyone else (Section 12, Appendix A defect #5) —
        # without this, the INSERT's implicit WITH CHECK (same predicate
        # as the SELECT policy) would reject it.
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=role,
                display_name=role,
                is_active=True,
            )
        )
    return user_id, email


async def _cleanup_user(user_id: uuid.UUID) -> None:
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        await session.execute(
            text("DELETE FROM refresh_token_families WHERE user_id = :id"), {"id": user_id}
        )
        await session.execute(text("DELETE FROM login_attempts"))
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


@pytest.fixture(autouse=True)
async def _reset_rate_limit_buckets():
    """Phase 1's login rate limit is per-email/per-IP in Valkey — reset
    between tests so one test's attempts don't 429 the next."""
    yield
    r = get_valkey_client()
    async for key in r.scan_iter("ratelimit:login:*"):
        await r.delete(key)


async def test_login_sets_httponly_cookies_not_a_json_token():
    """Section 7.4: the prior build kept the access token in JS memory
    (lost on refresh). This build must never put it in the JSON body."""
    user_id, email = await _make_user("case_officer")
    try:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert resp.status_code == 200
        assert "access_token" not in resp.json()
        assert "icm_access" in resp.cookies
        assert "icm_refresh" in resp.cookies
        assert "icm_csrf" in resp.cookies
        body = resp.json()
        assert body["csrf_token"] == resp.cookies["icm_csrf"]
    finally:
        await _cleanup_user(user_id)


async def test_wrong_password_is_rejected_with_generic_error():
    user_id, email = await _make_user("case_officer")
    try:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert resp.status_code == 401
    finally:
        await _cleanup_user(user_id)


async def test_lockout_after_threshold_failures():
    user_id, email = await _make_user("case_officer")
    try:
        from app.core.config import settings

        for _ in range(settings.lockout_threshold):
            resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
            assert resp.status_code == 401
        locked = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert locked.status_code == 423
    finally:
        await _cleanup_user(user_id)


async def test_totp_required_role_cannot_login_without_enrollment():
    user_id, email = await _make_user("bureau_head")
    try:
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert resp.status_code == 412
    finally:
        await _cleanup_user(user_id)


async def test_totp_required_role_full_flow():
    user_id, email = await _make_user("bureau_head")
    try:
        secret = pyotp.random_base32()
        async with SessionLocal() as session, session.begin():
            await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
            await session.execute(
                text("UPDATE users SET totp_secret = :s WHERE id = :id"), {"s": secret, "id": user_id}
            )

        code = pyotp.TOTP(secret).now()
        resp = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD, "totp_code": code}
        )
        assert resp.status_code == 200
    finally:
        await _cleanup_user(user_id)


async def test_refresh_rotates_token_and_reuse_is_detected():
    user_id, email = await _make_user("case_officer")
    try:
        login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200
        old_refresh_cookie = login.cookies["icm_refresh"]

        client.cookies.set("icm_refresh", old_refresh_cookie)
        refreshed = client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        new_refresh_cookie = refreshed.cookies["icm_refresh"]
        assert new_refresh_cookie != old_refresh_cookie

        # Reuse the OLD (already-rotated-away) refresh token.
        client.cookies.set("icm_refresh", old_refresh_cookie)
        reused = client.post("/api/v1/auth/refresh")
        assert reused.status_code == 401

        # The whole family is now revoked — even the latest token fails.
        client.cookies.set("icm_refresh", new_refresh_cookie)
        after_revocation = client.post("/api/v1/auth/refresh")
        assert after_revocation.status_code == 401
    finally:
        client.cookies.clear()
        await _cleanup_user(user_id)


async def test_logout_requires_csrf_token():
    user_id, email = await _make_user("case_officer")
    try:
        login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        client.cookies.set("icm_access", login.cookies["icm_access"])
        client.cookies.set("icm_csrf", login.cookies["icm_csrf"])

        no_csrf = client.post("/api/v1/auth/logout")
        assert no_csrf.status_code == 403

        with_csrf = client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": login.cookies["icm_csrf"]}
        )
        assert with_csrf.status_code == 204
    finally:
        client.cookies.clear()
        await _cleanup_user(user_id)
