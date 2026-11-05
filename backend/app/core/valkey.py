import asyncio

import redis.asyncio as redis_asyncio

from app.core.config import settings

_client: redis_asyncio.Redis | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_valkey_client() -> redis_asyncio.Redis:
    """Rebinds to a fresh client if the running event loop has changed
    since the client was created. A redis.asyncio connection pool binds its
    sockets to whichever loop is running when first used; reusing one
    client across different loops (e.g. Starlette's TestClient, which
    spins a new loop per `with TestClient(...) as client:` block) raises
    'Event loop is closed'. In production there's only ever one loop, so
    this is a no-op after the first call."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = redis_asyncio.from_url(settings.valkey_url, decode_responses=True)
        _client_loop = loop
    return _client


async def close_valkey_client() -> None:
    """Explicitly close and cleanup the cached Valkey client connection."""
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None
