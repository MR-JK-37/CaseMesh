"""Section 7.3: the alert catalogue's single choke point. Every alert
in the system is raised through `raise_alert()` so "each fires once per
threshold" (Section 7.3) is a real guarantee enforced by one unique
constraint (`alerts.dedup_key`), not a convention every call site has
to remember separately.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ALERT_CODES, Alert
from app.services.realtime import publish


async def raise_alert(
    session: AsyncSession,
    *,
    code: str,
    severity: str,
    resource_type: str,
    resource_id: uuid.UUID | None,
    message: str,
    dedup_key: str,
    payload: dict[str, Any] | None = None,
    channels: list[str] | None = None,
) -> Alert | None:
    """Inserts a new `Alert` and publishes it to the given real-time
    channels, unless an alert with this exact `dedup_key` already
    exists — in which case this is a no-op and returns `None`. Callers
    build `dedup_key` to mean "this specific threshold, for this
    specific resource" (e.g. `f"SLA_APPROACHING:{case_id}:{warn_days}"`
    so crossing a *different* warn window for the same case still
    raises a new alert, but re-scanning the same threshold never
    duplicates)."""
    if code not in ALERT_CODES:
        raise ValueError(f"Unknown alert code: {code}")

    existing = (await session.execute(select(Alert.id).where(Alert.dedup_key == dedup_key))).scalar_one_or_none()
    if existing is not None:
        return None

    alert = Alert(
        code=code,
        severity=severity,
        resource_type=resource_type,
        resource_id=resource_id,
        message=message,
        payload=payload or {},
        dedup_key=dedup_key,
    )
    try:
        # A SAVEPOINT, not session.rollback() — the caller's outer
        # transaction (e.g. a case event being appended) must survive a
        # lost dedup race intact; only this one insert should unwind.
        async with session.begin_nested():
            session.add(alert)
            await session.flush()
    except IntegrityError:
        # A concurrent raiser won the race on the same dedup_key — the
        # alert exists either way, which is the only guarantee this
        # function promises.
        return None

    for channel in channels or ["broadcast:all"]:
        await publish(
            session,
            channel=channel,
            event_type="alert_raised",
            payload={
                "alert_id": str(alert.id),
                "code": alert.code,
                "severity": alert.severity,
                "resource_type": alert.resource_type,
                "resource_id": str(alert.resource_id) if alert.resource_id else None,
                "message": alert.message,
            },
        )
    return alert
