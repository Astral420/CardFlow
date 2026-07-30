
import fakeredis
import pytest


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.token_store.redis_client", fake_client)
    yield fake_client
