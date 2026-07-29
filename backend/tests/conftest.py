"""Shared pytest fixtures.

The suite exercises route/dependency functions directly against an
in-memory sqlite DB rather than spinning up the full app or its external
services (see test_rbac.py's module docstring). This fixture keeps that
property true for Redis too: app.token_store (session revocation,
refresh-token families) is patched to talk to an in-memory fakeredis
stand-in instead of requiring a real Redis server just to run the tests.

Autouse + session-agnostic on purpose: every test gets a fresh fake Redis,
even ones that don't touch auth, so nothing can leak state between tests.
"""

import fakeredis
import pytest


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    # Patch the name inside app.token_store itself, not app.redis_client --
    # token_store did `from app.redis_client import redis_client`, which
    # binds its own local reference at import time. Patching the origin
    # module afterward wouldn't touch that already-bound reference.
    monkeypatch.setattr("app.token_store.redis_client", fake_client)
    yield fake_client
