"""Section 6.4: the transactional-outbox half of the real-time fabric.
`publish()` only ever writes a row in the caller's existing transaction
— it never touches Valkey directly, so a request that publishes an
event and then rolls back never leaks a phantom notification.
`relay_once()` (below) is the only thing that reads this table and
talks to Valkey, run by `scripts/run_relay.py`, a standalone polling
process — not an in-process FastAPI background task (that was tried
first and caused a real test-suite hang, see docs/decision-log.md) and
not a separately-deployed ARQ worker either (Section 10's worker infra
is unbuilt — see docs/limitations.md).

Event payloads are T1 data only (Section 6.4): a case ID, a status, an
actor role — never a remark or message body.
"""

import datetime as dt
import json
import uuid
from typing import Any

import redis.exceptions
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.valkey import get_valkey_client
from app.models import OutboxEvent

log = structlog.get_logger()


async def publish(session: AsyncSession, *, channel: str, event_type: str, payload: dict[str, Any]) -> OutboxEvent:
    event = OutboxEvent(channel=channel, event_type=event_type, payload=_json_safe(payload))
    session.add(event)
    await session.flush()
    return event


async def relay_once(limit: int = 100) -> int:
    """Section 6.4's relay worker: moves un-relayed `outbox_events` rows
    to Valkey Streams, one per channel (`rt:{channel}`), using an
    *explicit* stream ID of `f"{seq}-0"` rather than Valkey's
    auto-generated `*` — this is what lets a reconnecting client's
    `since_seq` (its own outbox seq watermark) map directly onto stream
    IDs for gap-free resume (`app/routers/realtime.py`), instead of
    needing a second ID-translation table.

    Run on a short poll interval by `scripts/run_relay.py` — see that
    script and this module's docstring for why it's a standalone
    process rather than an in-process background task. Also callable
    directly, which is how `tests/test_realtime.py` simulates "the
    relay processes outbox rows" deterministically instead of racing a
    background process.

    Per-row, not all-or-nothing: a single row whose `XADD` fails (found
    in practice when two relay processes ran concurrently by accident —
    the second's `XADD` for a row the first had already written
    collides on the explicit `f"{seq}-0"` ID and Valkey rejects it) is
    logged and marked relayed anyway rather than left to poison every
    later call — the original all-or-nothing version let one such row
    permanently wedge the queue, since every subsequent call re-selects
    the same oldest un-relayed row first and fails on it again before
    ever reaching newer rows. A `ResponseError` here means the stream
    already has this exact entry (another relay got there first), which
    is the one error safe to treat as success; anything else is a real
    Valkey problem and is re-raised so the caller's retry/backoff
    (`scripts/run_relay.py`'s loop) sees it."""
    r = get_valkey_client()
    relayed_count = 0
    async with SessionLocal() as session, session.begin():
        rows = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.relayed_at.is_(None)).order_by(OutboxEvent.seq).limit(limit)
            )
        ).scalars().all()
        for row in rows:
            try:
                await r.xadd(
                    f"rt:{row.channel}",
                    {"event_type": row.event_type, "payload": json.dumps(row.payload)},
                    id=f"{row.seq}-0",
                )
            except redis.exceptions.ResponseError as exc:
                log.warning("relay_xadd_id_collision", seq=row.seq, channel=row.channel, error=str(exc))
            row.relayed_at = dt.datetime.now(dt.UTC)
            relayed_count += 1
            await session.flush()
    return relayed_count


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
