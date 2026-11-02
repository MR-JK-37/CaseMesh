"""Shared, autouse fixtures for every test module — pytest discovers
this automatically, no import needed in individual test files.

`_reset_login_rate_limit_buckets_globally` fixes a real flakiness found
in Phase 5: `starlette.testclient.TestClient` always originates requests
from the same source IP, so every test file's logins share Section
7.4's per-IP login rate-limit bucket (`ratelimit:login:{ip_prefix}`,
20 attempts / 10 minutes). Individual test files had their own
`autouse` reset fixture (e.g. `test_cases_api.py`'s), but that only
resets after *that file's own* tests — a full-suite run across many
files could still cross the shared bucket's threshold depending on run
order, intermittently 429-ing an unrelated test's login. Resetting here,
after every single test regardless of which file it's in, removes the
shared-bucket cross-file accumulation entirely."""

import pytest

from app.core.valkey import get_valkey_client


@pytest.fixture(autouse=True)
async def _reset_login_rate_limit_buckets_globally():
    yield
    r = get_valkey_client()
    async for key in r.scan_iter("ratelimit:login:*"):
        await r.delete(key)
