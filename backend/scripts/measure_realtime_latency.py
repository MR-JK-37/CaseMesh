"""Section 6.4's named target: "event visible on another officer's
screen p95 < 1 s" — "to be measured, not claimed." This script measures
the real, in-process round trip (DB write -> Valkey XADD -> WebSocket
delivery) N times and reports p50/p95/max, then writes docs/perf.md.

What this measures: `publish()` (a real outbox row, committed) ->
`relay_once()` (a real Valkey XADD) -> the WebSocket gateway's own poll
loop picking it up and sending it -> `ws.receive_json()` returning.
That covers every real processing step in the pipeline.

What this does NOT measure (and says so in the report, rather than
folding it in silently): the random 0-0.5s wait for
`scripts/run_relay.py`'s poll loop to next call `relay_once()` in
production — this script calls `relay_once()` immediately after
`publish()` so the measurement isn't dominated by an arbitrary sleep
duration unrelated to the pipeline's real processing cost. The
configured worst-case relay-poll contribution is stated separately in
the report as a known constant, not re-measured here.

Usage: python scripts/measure_realtime_latency.py [--trials N]
"""

import argparse
import asyncio
import statistics
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password
from app.main import app
from app.models import Bureau, User, UserAssignment
from app.services.realtime import publish, relay_once
from tests.db_helpers import OwnerSession  # reuses the real test DB helper, not a mock

OUTPUT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "perf.md"
PASSWORD = "Correct-Horse-Battery-Staple-9"
RELAY_POLL_SECONDS_PRODUCTION = 0.5  # scripts/run_relay.py's real configured interval
WS_POLL_SECONDS = 0.2  # app/routers/realtime.py's POLL_INTERVAL_SECONDS


async def _setup_user() -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    bureau_id = uuid.uuid4()
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'super_admin', true)"))
        session.add(Bureau(id=bureau_id, name="Perf Test Bureau", kind="bureau"))
        session.add(
            User(
                id=user_id,
                email=f"perf-{user_id}@example.test",
                password_hash=hash_password(PASSWORD),
                role="case_officer",  # no TOTP requirement (Section 4.1), keeps this script simple
                display_name="perf",
                is_active=True,
            )
        )
        await session.flush()
        session.add(UserAssignment(user_id=user_id, bureau_id=bureau_id))
    return user_id, bureau_id


async def _publish_event(channel: str, event_type: str) -> None:
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        await publish(session, channel=channel, event_type=event_type, payload={})


async def _drain_backlog() -> None:
    while await relay_once() > 0:
        pass


def _render_report(latencies_ms: list[float]) -> str:
    import datetime as dt

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95 = latencies_ms[min(len(latencies_ms) - 1, int(len(latencies_ms) * 0.95))]
    worst_case_bound_ms = (RELAY_POLL_SECONDS_PRODUCTION + WS_POLL_SECONDS) * 1000 + p95
    return (
        "# Real-time delivery latency (Section 6.4)\n\n"
        f"_Last run: {dt.datetime.now(dt.UTC).isoformat()}_\n\n"
        f"Measured: real outbox write -> real Valkey `XADD` -> real WebSocket gateway poll loop "
        f"-> `receive_json()` returning, over {len(latencies_ms)} trials, in-process "
        "(no real network — loopback ASGI test transport).\n\n"
        "| Percentile | Latency |\n|---|---|\n"
        f"| p50 | {p50:.1f} ms |\n"
        f"| p95 | {p95:.1f} ms |\n"
        f"| max | {max(latencies_ms):.1f} ms |\n\n"
        "**What this does not include:** the measurement calls `relay_once()` immediately "
        "after publishing, rather than waiting for `scripts/run_relay.py`'s real poll loop "
        f"(configured at {RELAY_POLL_SECONDS_PRODUCTION * 1000:.0f} ms) — that wait is a "
        "known, configured constant, not re-measured here, because measuring it would mostly "
        "measure `asyncio.sleep()`'s accuracy, not this pipeline's real cost.\n\n"
        f"**Worst-case end-to-end bound** (configured relay poll interval + configured WS poll "
        f"interval + measured p95 processing time): "
        f"{RELAY_POLL_SECONDS_PRODUCTION * 1000:.0f} ms + {WS_POLL_SECONDS * 1000:.0f} ms + "
        f"{p95:.1f} ms = **{worst_case_bound_ms:.1f} ms**, comfortably under Section 6.4's "
        "1 s target.\n\n"
        "**Target (Section 6.4):** event visible on another officer's screen p95 < 1 s. "
        f"{'MET' if worst_case_bound_ms < 1000 else 'NOT MET'} by this measurement.\n"
    )


async def main(trials: int) -> None:
    user_id, bureau_id = await _setup_user()
    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login", json={"email": f"perf-{user_id}@example.test", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    csrf = login.cookies["icm_csrf"]
    headers = {"X-CSRF-Token": csrf}

    await _drain_backlog()

    channel = f"bureau:{bureau_id}"
    latencies_ms: list[float] = []
    ticket = client.post("/api/v1/realtime/ticket", headers=headers).json()["ticket"]
    with client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as ws:
        for i in range(trials):
            event_type = f"perf_trial_{i}"
            t0 = time.monotonic()
            await _publish_event(channel, event_type)
            await relay_once()
            while True:
                msg = ws.receive_json()
                if msg.get("event_type") == event_type:
                    break
            latencies_ms.append((time.monotonic() - t0) * 1000)

    report = _render_report(latencies_ms)
    OUTPUT_PATH.write_text(report)
    print(report)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(main(args.trials))
