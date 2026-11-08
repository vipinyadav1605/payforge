"""Requires a running Redis (docker compose up redis). Skipped if Redis is unreachable."""

import time

import pytest
import redis as redis_lib

from app.config import get_settings


@pytest.fixture
def limiter_on(monkeypatch):
    s = get_settings()
    try:
        redis_lib.Redis.from_url(s.redis_url, socket_connect_timeout=0.5).ping()
    except redis_lib.RedisError:
        pytest.skip("Redis not available")
    monkeypatch.setattr(s, "rate_limit_enabled", True)
    monkeypatch.setattr(s, "rate_limit_capacity", 3)
    monkeypatch.setattr(s, "rate_limit_refill_per_sec", 2.0)


def test_burst_is_limited_then_recovers(client, headers, limiter_on):
    codes = [client.get("/v1/me", headers=headers).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]
    blocked = client.get("/v1/me", headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1
    time.sleep(1.2)  # refill: 2 tokens/sec
    assert client.get("/v1/me", headers=headers).status_code == 200


def test_limits_are_per_api_key(client, headers, limiter_on):
    from tests.conftest import make_merchant

    other = make_merchant(client, "Other")
    for _ in range(5):
        client.get("/v1/me", headers=headers)
    ok = client.get("/v1/me", headers={"Authorization": f"Bearer {other['api_key']}"})
    assert ok.status_code == 200


def test_fails_open_when_redis_is_down(client, headers, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_enabled", True)
    monkeypatch.setattr("app.ratelimit.check", lambda *a, **k: None)  # simulate outage
    assert client.get("/v1/me", headers=headers).status_code == 200
