
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
