"""Section 6.4's relay worker: a standalone process, matching the
pattern `scripts/rebuild_projection.py` and `scripts/eval_overlap.py`
already use rather than an in-process FastAPI background task (see
app/main.py's comment for why — a real bug, not a style preference).

Run alongside the API (`uv run uvicorn app.main:app ...`) during local
dev / the SIH demo:

    uv run python3 scripts/run_relay.py

Not yet wired into infra/docker-compose.yml as its own service, and not
a separately-deployed ARQ worker (Section 10's worker infra is still
unbuilt) — see docs/limitations.md. Polls every 0.5s; exits cleanly on
SIGINT/SIGTERM.
"""

import asyncio
import signal

import structlog

from app.services.realtime import relay_once

log = structlog.get_logger()

POLL_SECONDS = 0.5


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info("relay_started")
    while not stop.is_set():
        try:
            count = await relay_once()
            if count:
                log.info("relay_batch", count=count)
        except Exception as exc:  # noqa: BLE001 — one bad iteration must never kill the worker
            log.warning("relay_iteration_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
        except TimeoutError:
            pass
    log.info("relay_stopped")


if __name__ == "__main__":
    asyncio.run(main())
