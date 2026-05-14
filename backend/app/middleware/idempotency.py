"""Idempotency-Key support for unsafe HTTP methods.

Clients pass `Idempotency-Key: <uuid>` on POST/PUT/PATCH. We hash
(user, method, path, key) and cache the response in Redis for 24h.
A retry of the same key returns the cached response instead of
re-executing the handler — safe re-tries for flaky networks.
"""

import hashlib
import json

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.redis_client import get_redis
from app.core.security import decode_token

IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TTL = 24 * 60 * 60


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in IDEMPOTENT_METHODS:
            return await call_next(request)
        key = request.headers.get("idempotency-key")
        if not key:
            return await call_next(request)

        cache_key = self._cache_key(request, key)
        redis = get_redis()
        try:
            cached = await redis.get(cache_key)
        except Exception:
            cached = None

        if cached:
            payload = json.loads(cached)
            return Response(
                content=payload["body"].encode("utf-8"),
                status_code=payload["status"],
                headers={**payload["headers"], "Idempotent-Replay": "true"},
                media_type=payload["headers"].get("content-type"),
            )

        response = await call_next(request)

        # Only cache successful responses; surfacing a stale 500 would be worse than retrying.
        if 200 <= response.status_code < 300:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                await redis.set(
                    cache_key,
                    json.dumps(
                        {
                            "status": response.status_code,
                            "headers": {
                                k.decode(): v.decode() for k, v in response.raw_headers
                            },
                            "body": body.decode("utf-8", errors="replace"),
                        }
                    ),
                    ex=TTL,
                )
            except Exception:
                pass
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        return response

    @staticmethod
    def _cache_key(request: Request, key: str) -> str:
        auth = request.headers.get("authorization", "")
        ident = "anon"
        if auth.lower().startswith("bearer "):
            try:
                ident = decode_token(auth[7:])["sub"]
            except Exception:
                pass
        h = hashlib.sha256(
            f"{ident}|{request.method}|{request.url.path}|{key}".encode()
        ).hexdigest()
        return f"idem:{h}"
