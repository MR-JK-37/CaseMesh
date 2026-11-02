from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_always_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_reports_database_state_honestly():
    """/ready must never fabricate a ready state: 200 only with a real DB
    connection, 503 with an honest reason otherwise (Section 0 rule 2's
    'never fabricate success' applies to infra checks too)."""
    resp = client.get("/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    if resp.status_code == 200:
        assert body["database"] == "ok"
    else:
        assert body["database"] == "unreachable"
