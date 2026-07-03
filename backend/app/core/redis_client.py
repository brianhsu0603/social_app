import asyncio
from typing import AsyncIterator

import redis.asyncio as redis

from app.core.config import settings

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def pubsub_listen(channel: str, stop_event: asyncio.Event) -> AsyncIterator[str]:
    """Yield raw message payloads from a Redis pub/sub channel until stop_event is set."""
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel)
    try:
        while not stop_event.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                yield msg["data"]
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
