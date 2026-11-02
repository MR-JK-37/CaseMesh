from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent


def emit_event(session: AsyncSession, *, channel: str, event_type: str, payload: dict) -> None:
    """Stages an outbox row on the caller's own session/transaction —
    deliberately NOT async-flushed or committed here. If the caller's
    transaction rolls back (e.g. a blocked registration), this row rolls
    back with it. Section 6: 'No event for a rolled-back change.'"""
    session.add(OutboxEvent(channel=channel, event_type=event_type, payload=payload))
