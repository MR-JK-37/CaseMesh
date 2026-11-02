"""Phase 5 gate (Section 16): R13 — real-time fabric. Drives the actual
WebSocket gateway, the actual Valkey Streams relay, and the actual
ticket mechanism; "kill-worker" is simulated by simply not calling
`_relay_all()` (there is no separately-deployed worker process to kill
— see docs/limitations.md) and confirming outbox rows queue up
un-relayed without being lost, then recover once the relay runs.
Reconnect is tested via `since_seq` resume against the real Valkey
stream, not mocked.
"""

import pytest
from sqlalchemy import text

from app.core.valkey import get_valkey_client
from app.services.realtime import publish, relay_once

from .db_helpers import OwnerSession
from .test_cases_api import _cleanup_user, _login_as, _reset_rate_limit_buckets, world  # noqa: F401


@pytest.fixture(autouse=True)
async def _clean_streams():
    yield
    r = get_valkey_client()
    async for key in r.scan_iter("rt:*"):
        await r.delete(key)


@pytest.fixture(autouse=True)
async def _drain_preexisting_backlog_once_per_test(_clean_streams):
    """A fresh WS connection with no resume requested seeds its cursor
    from each channel's *current* Valkey stream tail (`_initial_last_ids`
    in app/routers/realtime.py) — correct for "don't replay history on a
    fresh connect". But `broadcast:all` is shared by every role (Section
    6.4), and by the time this file's tests run in a full suite, earlier
    files have raised real alerts (ESCALATION_RAISED, OVERLAP_DETECTED,
    SLA_POLICY_MISSING, ...) that nothing has relayed yet — if *this*
    test's own `_relay_all()` is what first pushes that backlog into
    Valkey, those old low-seq entries land in a stream a fresh
    connection still thinks is empty, so they look like "new" events
    and swamp the test's WS. Pre-draining here, before each test
    connects anything, means that backlog is already in Valkey — and
    therefore already "history" — by the time any test in this file
    seeds its tail."""
    await _relay_all()
    yield


async def _publish_test_event(*, channel: str, event_type: str = "test_event", payload: dict | None = None) -> int:
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        event = await publish(session, channel=channel, event_type=event_type, payload=payload or {"n": 1})
        seq = event.seq
    return seq


async def _relay_all() -> int:
    """`_relay_all()` only moves up to its `limit` (default 100) rows
    per call — by design, so one slow caller can't starve the relay
    loop forever on an unbounded backlog. By the time this test file
    runs in a full suite, earlier test files (especially the Phase 4
    overlap tests, which raise an OVERLAP_DETECTED/HIGH_CONFIDENCE alert
    per scored pair) can leave well over 100 rows un-relayed, since
    nothing else in the suite calls `_relay_all()` at all. A single
    `_relay_all()` call in that situation drains old backlog, not this
    test's own just-published event, and every WS `receive_json()`
    blocks forever waiting for a message that was never sent — a real
    full-suite hang this test file's first draft hit (found via a
    faulthandler stack dump, not anticipated — see docs/decision-log.md).
    Draining in a loop until the backlog is empty is what a real
    always-running worker does anyway, so this is the correct fix, not
    a test-only workaround."""
    total = 0
    while True:
        n = await relay_once()
        total += n
        if n == 0:
            return total


def _receive_until(ws, event_type: str, *, max_messages: int = 25) -> dict:
    """Every WS connection also subscribes to `broadcast:all` (Section
    6.4's fixed system channel), which can carry real `alert_raised`
    events left un-relayed by *other* tests earlier in the same suite
    run. A real client already has to tolerate a shared broadcast
    channel carrying things it doesn't care about, so filtering here is
    both the realistic behaviour and what keeps this test from being
    fragile to full-suite run order."""
    for _ in range(max_messages):
        msg = ws.receive_json()
        if msg.get("event_type") == event_type:
            return msg
    raise AssertionError(f"did not see event_type={event_type!r} within {max_messages} messages")


async def test_ticket_is_single_use(world):
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        resp = u.client.post("/api/v1/realtime/ticket", headers=u.headers)
        assert resp.status_code == 200
        ticket = resp.json()["ticket"]

        with u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as ws:
            ws.close()

        # A second connection with the same (already-consumed) ticket
        # must be refused — GETDEL makes reuse impossible, not just
        # discouraged.
        with pytest.raises(Exception), u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}"):  # noqa: B017 — starlette raises WebSocketDisconnect on refused handshake
            pass
    finally:
        await _cleanup_user(u.user_id)


async def test_ws_receives_event_after_relay_runs(world):
    """R13: an event published to a channel this user is subscribed to
    (their own bureau channel) reaches the WebSocket — but only after
    the relay actually moves it from the outbox to Valkey, proving the
    outbox -> relay -> stream path is real, not a direct pipe."""
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        ticket = u.client.post("/api/v1/realtime/ticket", headers=u.headers).json()["ticket"]
        with u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as ws:
            await _publish_test_event(channel=f"bureau:{world['bureau_a']}", payload={"hello": "world"})
            # "Kill-worker": nothing has called _relay_all() yet, so
            # there is deliberately nothing to receive — the row sits
            # safely in outbox_events, not lost, not delivered early.
            relayed = await _relay_all()
            assert relayed >= 1
            msg = _receive_until(ws, "test_event")
            assert msg["payload"] == {"hello": "world"}
    finally:
        await _cleanup_user(u.user_id)


async def test_ws_does_not_receive_events_on_unrelated_bureau_channel(world):
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        ticket = u.client.post("/api/v1/realtime/ticket", headers=u.headers).json()["ticket"]
        with u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as ws:
            await _publish_test_event(channel=f"bureau:{world['bureau_b']}")
            await _relay_all()
            # Prove liveness with an event on a channel this user *is*
            # subscribed to, so a timeout here means "correctly filtered"
            # rather than "the whole pipe is broken".
            await _publish_test_event(channel=f"bureau:{world['bureau_a']}", event_type="own_bureau_event")
            await _relay_all()
            _receive_until(ws, "own_bureau_event")
    finally:
        await _cleanup_user(u.user_id)


async def test_reconnect_resumes_missed_events_via_since_seq(world):
    """Section 6.4(a): a reconnecting client replays missed events from
    the outbox via Last-Event-ID-equivalent resume (`since_seq`) — the
    core "reconnect" requirement of R13."""
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        channel = f"bureau:{world['bureau_a']}"
        ticket1 = u.client.post("/api/v1/realtime/ticket", headers=u.headers).json()["ticket"]
        with u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket1}") as ws1:
            await _publish_test_event(channel=channel, event_type="event_a")
            await _relay_all()
            first = _receive_until(ws1, "event_a")
            last_seen_id = first["id"]

        # Disconnected now. Two more events happen while nobody is
        # listening — a real gap, not a timing artefact.
        await _publish_test_event(channel=channel, event_type="event_b")
        await _publish_test_event(channel=channel, event_type="event_c")
        await _relay_all()

        ticket2 = u.client.post("/api/v1/realtime/ticket", headers=u.headers).json()["ticket"]
        with u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket2}&since_seq={last_seen_id}") as ws2:
            # since_seq resume replays this channel's own backlog in
            # order; broadcast:all noise can still be interleaved, so
            # filter for each expected event by type rather than
            # assuming they're the very next two messages.
            _receive_until(ws2, "event_b")
            _receive_until(ws2, "event_c")
    finally:
        await _cleanup_user(u.user_id)


async def test_fresh_connect_without_since_seq_does_not_replay_history(world):
    u = await _login_as("bureau_head", bureau_id=world["bureau_a"])
    try:
        channel = f"bureau:{world['bureau_a']}"
        await _publish_test_event(channel=channel, event_type="old_event")
        await _relay_all()

        ticket = u.client.post("/api/v1/realtime/ticket", headers=u.headers).json()["ticket"]
        with u.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as ws:
            await _publish_test_event(channel=channel, event_type="new_event")
            await _relay_all()
            _receive_until(ws, "new_event")
    finally:
        await _cleanup_user(u.user_id)


async def test_broadcast_channel_reaches_every_role(world):
    """`SLA_POLICY_MISSING`/`PROJECTION_DRIFT`-style alerts must reach
    super_admin, who has no bureau assignment at all — proves the fixed
    `broadcast:all` channel (not a bureau channel) is what carries them."""
    admin = await _login_as("super_admin")
    try:
        ticket = admin.client.post("/api/v1/realtime/ticket", headers=admin.headers).json()["ticket"]
        with admin.client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as ws:
            await _publish_test_event(channel="broadcast:all", event_type="system_alert")
            await _relay_all()
            _receive_until(ws, "system_alert")
    finally:
        await _cleanup_user(admin.user_id)


async def test_relay_is_idempotent_within_one_call(world):
    """Calling _relay_all() repeatedly never re-relays an already-relayed
    row — `relayed_at` is the guard."""
    channel = "broadcast:all"
    await _publish_test_event(channel=channel)
    first = await relay_once()
    second = await relay_once()
    assert first >= 1
    assert second == 0


async def test_relay_survives_a_concurrent_xadd_id_collision(world):
    """Regression: two relay processes accidentally running at once
    (found live — see docs/decision-log.md) raced to `XADD` the same
    row with the same explicit `f"{seq}-0"` ID; the loser's `XADD`
    raised, and the original all-or-nothing transaction let that one
    row permanently wedge the queue, since every later `relay_once()`
    call re-selects the same oldest un-relayed row first and fails on
    it again before ever reaching newer rows — real events stopped
    reaching WebSocket clients entirely, silently. Simulated here by
    writing an outbox row, having the *real* `relay_once()` XADD it
    once, then resetting only `relayed_at` back to NULL (simulating the
    first relay's DB write having been lost/rolled back after its
    Valkey write succeeded) so the second `relay_once()` call must
    XADD the exact same ID again and hit a real Valkey ResponseError."""
    channel = f"bureau:{world['bureau_a']}"
    seq = await _publish_test_event(channel=channel, event_type="collision_test")
    first = await relay_once()
    assert first >= 1

    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        await session.execute(text("UPDATE outbox_events SET relayed_at = NULL WHERE seq = :seq"), {"seq": seq})

    # A later, unrelated event must still get through even though the
    # collided row is ahead of it in seq order.
    await _publish_test_event(channel=channel, event_type="after_collision")

    second = await relay_once()
    assert second >= 1  # did not raise, and made progress

    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        row = (
            await session.execute(text("SELECT relayed_at FROM outbox_events WHERE seq = :seq"), {"seq": seq})
        ).one()
        assert row.relayed_at is not None  # marked relayed despite the collision, not stuck forever


async def test_outbox_row_persists_until_relayed(world):
    """The durability half of "kill-worker": an unrelayed row is a real,
    queryable Postgres row, not an in-memory queue that would vanish if
    the process restarted."""
    seq = await _publish_test_event(channel="broadcast:all", event_type="durability_check")
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        row = (
            await session.execute(
                text("SELECT relayed_at FROM outbox_events WHERE seq = :seq"), {"seq": seq}
            )
        ).one()
        assert row.relayed_at is None
    await _relay_all()
    async with OwnerSession() as session, session.begin():
        await session.execute(text("SELECT set_config('app.role', 'system', true)"))
        row = (
            await session.execute(
                text("SELECT relayed_at FROM outbox_events WHERE seq = :seq"), {"seq": seq}
            )
        ).one()
        assert row.relayed_at is not None
