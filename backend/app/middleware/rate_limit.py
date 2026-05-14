"""Token-bucket rate limiter backed by Redis.

Keyed by (user_id or client IP, route prefix). The Lua script is atomic
so concurrent requests can't race past the limit. Returns 429 + a
Retry-After hint when the bucket is empty.
"""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.redis_client import get_redis
from app.core.security import decode_token

# Atomic token-bucket refill+consume. Returns (allowed, retry_after_seconds).
_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(data[1]) or capacity
local updated_at = tonumber(data[2]) or now

local elapsed = math.max(0, now - updated_at)
tokens = math.min(capacity, tokens + elapsed * refill_per_sec)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_after = math.ceil((1 - tokens) / refill_per_sec)
end

redis.call('HMSET', key, 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', key, 3600)
return {allowed, retry_after}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, capacity: int = 120, refill_per_sec: float = 2.0):
        super().__init__(app)
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._script_sha: str | None = None

    async def dispatch(self, request: Request, call_next):
        # Health/metrics endpoints should never be throttled.
        if request.url.path in {"/health", "/metrics"}:
            return await call_next(request)

        identity = self._identity_from(request)
        key = f"rl:{identity}:{request.url.path.split('/', 2)[1] or 'root'}"
        redis = get_redis()
        if self._script_sha is None:
            self._script_sha = await redis.script_load(_LUA)

        try:
            allowed, retry_after = await redis.evalsha(
                self._script_sha,
                1,
                key,
                self.capacity,
                self.refill_per_sec,
                int(time.time()),
            )
        except Exception:
            # Fail open: if Redis is unavailable, don't take the app down with it.
            return await call_next(request)

        if not int(allowed):
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(int(retry_after))},
            )
        return await call_next(request)

    @staticmethod
    def _identity_from(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                return f"u:{decode_token(auth[7:])['sub']}"
            except Exception:
                pass
        # X-Forwarded-For is set by the ingress; falling back to peer IP otherwise.
        xff = request.headers.get("x-forwarded-for")
        return f"ip:{(xff.split(',')[0].strip() if xff else (request.client.host if request.client else 'anon'))}"
