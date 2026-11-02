# Real-time delivery latency (Section 6.4)

_Last run: 2026-10-29T05:22:31.956069+00:00_

Measured: real outbox write -> real Valkey `XADD` -> real WebSocket gateway poll loop -> `receive_json()` returning, over 20 trials, in-process (no real network — loopback ASGI test transport).

| Percentile | Latency |
|---|---|
| p50 | 205.2 ms |
| p95 | 209.2 ms |
| max | 209.2 ms |

**What this does not include:** the measurement calls `relay_once()` immediately after publishing, rather than waiting for `scripts/run_relay.py`'s real poll loop (configured at 500 ms) — that wait is a known, configured constant, not re-measured here, because measuring it would mostly measure `asyncio.sleep()`'s accuracy, not this pipeline's real cost.

**Worst-case end-to-end bound** (configured relay poll interval + configured WS poll interval + measured p95 processing time): 500 ms + 200 ms + 209.2 ms = **909.2 ms**, comfortably under Section 6.4's 1 s target.

**Target (Section 6.4):** event visible on another officer's screen p95 < 1 s. MET by this measurement.
