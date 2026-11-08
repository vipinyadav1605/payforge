"""Distributed token-bucket rate limiter backed by Redis.

The whole check-and-update runs inside ONE Lua script, so it is atomic even when many API
replicas hit the same bucket. Redis' own clock (TIME) is used so replicas can't disagree.
If Redis is unreachable we fail OPEN (serve the request) rather than take payments down.
"""

import logging
from dataclasses import dataclass

import redis

from .config import get_settings

log = logging.getLogger("payforge.ratelimit")

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)
local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, math.ceil(capacity / rate) * 2 + 1)
local retry = 0
if allowed == 0 then
  retry = (cost - tokens) / rate
end
return {allowed, tostring(tokens), tostring(retry)}
"""


@dataclass
class RateResult:
    allowed: bool
    remaining: float
    retry_after: float


_client: redis.Redis | None = None
_script = None


def _get_script():
    global _client, _script
    if _script is None:
        _client = redis.Redis.from_url(
            get_settings().redis_url, socket_timeout=0.25, socket_connect_timeout=0.25
        )
        _script = _client.register_script(TOKEN_BUCKET_LUA)
    return _script


def check(bucket_key: str, capacity: int, refill_per_sec: float, cost: int = 1) -> RateResult | None:
    """Returns None if the limiter is unavailable (caller should fail open)."""
    try:
        allowed, tokens, retry = _get_script()(
            keys=[f"rl:{bucket_key}"], args=[capacity, refill_per_sec, cost]
        )
        return RateResult(bool(int(allowed)), float(tokens), float(retry))
    except redis.RedisError as exc:
        log.warning("rate limiter unavailable, failing open: %s", exc)
        return None
