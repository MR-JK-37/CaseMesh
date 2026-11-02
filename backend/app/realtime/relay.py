import json

import redis.asyncio as redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent


async def relay_pending(session: AsyncSession, redis_client: redis.Redis, *, limit: int = 100) -> int:
    """Reads unpublished outbox rows and PUBLISHes each to its Redis
    channel, then marks it published. Runs as a separate step from the
    business transaction (Section 6) — this function's own commit is
    independent of whatever wrote the rows."""
    rows = (
        await session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
    ).scalars().all()

    for row in rows:
        message = json.dumps(
            {"event_type": row.event_type, "payload": row.payload, "id": str(row.id)}
        )
        await redis_client.publish(row.channel, message)

    if rows:
        await session.execute(
            OutboxEvent.__table__.update()
            .where(OutboxEvent.id.in_([r.id for r in rows]))
            .values(published_at=func.now())
        )
        await session.commit()

    return len(rows)
