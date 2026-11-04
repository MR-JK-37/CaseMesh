import sentry_sdk
import structlog
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.routers import (
    alerts,
    auth,
    cases,
    dashboard,
    imports,
    institutions,
    overlap,
    realtime,
    reference,
    reports,
    sessions,
    system,
    totp,
    users,
    views,
)

log = structlog.get_logger()

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)
    log.info("sentry_enabled")
else:
    log.info("sentry_not_configured")

# Section 6.4's relay worker (app/services/realtime.py#relay_once) is run
# by scripts/run_relay.py, a standalone process — NOT an in-process
# FastAPI lifespan background task. An earlier version of this file did
# start it from `lifespan`, which seemed simpler, but
# starlette.testclient.TestClient starts a fresh ASGI lifespan (and so a
# fresh infinite polling task bound to that test's own event loop) on
# every `with client.websocket_connect(...)` call; across a 90+ test
# suite that leaked dozens of never-cancelled loops competing for the
# same shared engine's connection pool and hung the whole suite solid
# with no stack trace — a real bug found by the full suite (not one
# file) timing out, not anticipated. A separate script matches
# `scripts/rebuild_projection.py`/`scripts/eval_overlap.py`'s existing
# pattern and sidesteps the whole class of problem; see
# docs/decision-log.md and docs/limitations.md.
app = FastAPI(
    title="CaseMesh — AICTE Inter-Institutional Case Monitor API",
    version="0.1.0",
    description="Backend API for CaseMesh grievance deduplication and inter-institutional case coordination",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Defense in depth alongside Caddy's headers (infra/Caddyfile) — the
    API is sometimes hit directly in dev/CI without the proxy in front of
    it, and Appendix A's defect #5 ("no security headers anywhere") is
    exactly what this guards against at the app layer too."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(totp.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(reference.router, prefix="/api/v1")
app.include_router(imports.router, prefix="/api/v1")
app.include_router(institutions.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(overlap.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(realtime.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(views.router, prefix="/api/v1")

_engine = create_async_engine(settings.database_url, pool_pre_ping=True)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness only: process is up. No dependency checks."""
    return {"status": "ok"}


@app.get("/ready")
async def ready(response: Response) -> dict[str, str]:
    """Readiness: can the API actually reach Postgres."""
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:  # noqa: BLE001 — a readiness probe must stay up for any DB failure mode
        log.warning("ready_check_failed", error=str(exc))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": "unreachable"}
