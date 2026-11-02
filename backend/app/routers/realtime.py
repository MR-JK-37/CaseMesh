"""Section 6.4: the WebSocket gateway (+ SSE fallback) half of the
real-time fabric. The relay (`app/services/realtime.py#relay_once`)
writes events into per-channel Valkey Streams (`rt:{channel}`); this
router only ever reads from Valkey, never Postgres, once a connection
is established — REST stays the source of truth for T2 content
(Section 6.4: "clients fetch T2 over REST with their own
authorisation"), these channels carry T1 data only.
"""

import asyncio
import json
import secrets
import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.deps import Principal, get_current_principal, require_csrf
from app.core.valkey import get_valkey_client

router = APIRouter(prefix="/realtime", tags=["realtime"])

TICKET_TTL_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.2
HEARTBEAT_INTERVAL_SECONDS = 25.0


def _channels_for(role: str, bureau_ids: list[str], user_id: str) -> list[str]:
    """Section 6.4's channel list, narrowed to what Phase 5 actually
    publishes to (`user:{id}`, `bureau:{id}`, and a fixed `broadcast:all`
    for system-level alerts like `SLA_POLICY_MISSING`/`PROJECTION_DRIFT`
    that must reach `super_admin`, who has no bureau assignment at all
    — `region:{id}`/`institution:{id}`/`case:{id}`/`dashboard:{scope}`
    are not wired to a publisher yet, see docs/limitations.md)."""
    return [f"user:{user_id}", "broadcast:all"] + [f"bureau:{b}" for b in bureau_ids]


class TicketOut(BaseModel):
    ticket: str
    expires_in: int


@router.post("/ticket", response_model=TicketOut, dependencies=[Depends(require_csrf)])
async def issue_ticket(request: Request, principal: Principal = Depends(get_current_principal)):
    """Section 6.4(c): a one-time, 30 s, single-use ticket bound to the
    user and an IP /24 prefix. A WS/SSE connection can't carry the
    double-submit CSRF header a normal `fetch()` can, so the short-lived
    ticket is the subscribe-time credential instead — consumed exactly
    once, by `_consume_ticket`'s `GETDEL`."""
    r = get_valkey_client()
    ticket = secrets.token_urlsafe(24)
    client_host = request.client.host if request.client else "0.0.0.0"
    ip_prefix = ".".join(client_host.split(".")[:3])
    claims = {
        "user_id": principal.user_id,
        "role": principal.role,
        "bureau_ids": list(principal.bureau_ids),
        "ip_prefix": ip_prefix,
    }
    await r.set(f"rt:ticket:{ticket}", json.dumps(claims), ex=TICKET_TTL_SECONDS)
    return TicketOut(ticket=ticket, expires_in=TICKET_TTL_SECONDS)


async def _consume_ticket(ticket: str, client_ip: str | None) -> dict | None:
    r = get_valkey_client()
    raw = await r.getdel(f"rt:ticket:{ticket}")
    if raw is None:
        return None
    claims = json.loads(raw)
    if client_ip:
        ip_prefix = ".".join(client_ip.split(".")[:3])
        if ip_prefix != claims["ip_prefix"]:
            return None
    return claims


async def _initial_last_ids(channels: list[str], since_seq: str) -> dict[str, str]:
    """`since_seq == "0"` means "no resume requested" — a fresh connect
    should only see events from here on, not the channel's whole
    history, so each channel's cursor starts at its *current* tail
    (found via `XREVRANGE ... COUNT 1`), not the beginning of the
    stream. A real `since_seq` (a client's own last-seen outbox seq)
    is used as-is across every channel — Section 6.4(a)'s resume."""
    r = get_valkey_client()
    if since_seq != "0":
        return {ch: f"{since_seq}-0" for ch in channels}
    last_ids: dict[str, str] = {}
    for ch in channels:
        tail = await r.xrevrange(f"rt:{ch}", count=1)
        last_ids[ch] = tail[0][0] if tail else "0"
    return last_ids


async def _poll_channels(channels: list[str], last_ids: dict[str, str]) -> list[tuple[str, str, dict]]:
    r = get_valkey_client()
    events: list[tuple[str, str, dict]] = []
    for ch in channels:
        start = f"({last_ids[ch]}" if last_ids[ch] != "0" else "-"
        rows = await r.xrange(f"rt:{ch}", min=start, max="+")
        for entry_id, fields in rows:
            events.append((ch, entry_id, fields))
            last_ids[ch] = entry_id
    events.sort(key=lambda e: tuple(int(p) for p in e[1].split("-")))
    return events


def _serialize(ch: str, entry_id: str, fields: dict) -> dict:
    return {
        "id": entry_id.split("-")[0],
        "channel": ch,
        "event_type": fields.get("event_type"),
        "payload": json.loads(fields.get("payload", "{}")),
    }


@router.websocket("/ws")
async def realtime_ws(websocket: WebSocket, ticket: str, since_seq: str = "0"):
    claims = await _consume_ticket(ticket, websocket.client.host if websocket.client else None)
    if claims is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    channels = _channels_for(claims["role"], claims["bureau_ids"], claims["user_id"])
    last_ids = await _initial_last_ids(channels, since_seq)
    last_heartbeat = time.monotonic()
    try:
        while True:
            events = await _poll_channels(channels, last_ids)
            for ch, entry_id, fields in events:
                await websocket.send_json(_serialize(ch, entry_id, fields))
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                await websocket.send_json({"event_type": "heartbeat"})
                last_heartbeat = now
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return


@router.get("/sse")
async def realtime_sse(request: Request, ticket: str, since_seq: str = "0"):
    """SSE fallback (Section 6.4(e)) for proxies that break WebSockets.
    `Last-Event-ID`, when the browser's EventSource sends it on
    reconnect, takes priority over the `since_seq` query param."""
    claims = await _consume_ticket(ticket, request.client.host if request.client else None)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired ticket")
    effective_since = request.headers.get("last-event-id") or since_seq
    channels = _channels_for(claims["role"], claims["bureau_ids"], claims["user_id"])
    last_ids = await _initial_last_ids(channels, effective_since)

    async def event_stream():
        nonlocal last_ids
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            events = await _poll_channels(channels, last_ids)
            for ch, entry_id, fields in events:
                data = json.dumps(_serialize(ch, entry_id, fields))
                event_type = fields.get("event_type", "message")
                yield f"id: {entry_id.split('-')[0]}\nevent: {event_type}\ndata: {data}\n\n"
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                yield ": heartbeat\n\n"
                last_heartbeat = now
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
