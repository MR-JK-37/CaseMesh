import hashlib
import hmac
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AuditLogEntry

GENESIS_HASH = "0" * 64


async def append_audit_entry(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
) -> AuditLogEntry:
    """Section 8/M12: each row's `row_hash` chains from the previous row's
    hash, so altering or deleting a past entry breaks every hash after it.
    This only works as a real guarantee combined with `apaar_app` never
    having UPDATE/DELETE on this table (the migration's GRANT, not just
    this function's good behavior)."""
    last = (
        await session.execute(
            select(AuditLogEntry.row_hash).order_by(AuditLogEntry.seq.desc()).limit(1)
        )
    ).scalar_one_or_none()
    prev_hash = last or GENESIS_HASH

    canonical = json.dumps(
        {
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "actor_role": actor_role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
    ).encode("utf-8")
    row_hash = hmac.new(settings.app_secret_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()

    entry = AuditLogEntry(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> bool:
    """Recomputes every row's hash from its neighbors and compares —
    used by the integrity-check path and by tests. O(n); fine for a
    prototype's audit log size, not meant for a multi-million-row table
    without a checkpoint/anchor scheme (Section 11's 'anchor the chain
    head outside the DB' is not built — see limitations.md)."""
    rows = (await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.seq))).scalars().all()
    expected_prev = GENESIS_HASH
    for row in rows:
        canonical = json.dumps(
            {
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "actor_role": row.actor_role,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "prev_hash": expected_prev,
            },
            sort_keys=True,
        ).encode("utf-8")
        expected_hash = hmac.new(
            settings.app_secret_key.encode("utf-8"), canonical, hashlib.sha256
        ).hexdigest()
        if row.prev_hash != expected_prev or row.row_hash != expected_hash:
            return False
        expected_prev = row.row_hash
    return True
