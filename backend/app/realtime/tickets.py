import json
import secrets

import redis.asyncio as redis

TICKET_TTL_SECONDS = 60
TICKET_KEY_PREFIX = "ws-ticket:"


async def issue_ticket(
    redis_client: redis.Redis, *, user_id: str, role: str, institution_id: str | None
) -> str:
    """One-time WS ticket obtained over REST (Section 6: 'never JWT in
    URLs'). Short TTL, consumed exactly once by `consume_ticket`."""
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": user_id, "role": role, "institution_id": institution_id})
    await redis_client.set(f"{TICKET_KEY_PREFIX}{token}", payload, ex=TICKET_TTL_SECONDS)
    return token


async def consume_ticket(redis_client: redis.Redis, token: str) -> dict | None:
    """GETDEL is atomic server-side (Redis >= 6.2), so the same ticket can
    never be consumed twice even by two near-simultaneous connection
    attempts — unlike a separate GET then DELETE, which would race."""
    key = f"{TICKET_KEY_PREFIX}{token}"
    payload = await redis_client.getdel(key)
    if payload is None:
        return None
    return json.loads(payload)
