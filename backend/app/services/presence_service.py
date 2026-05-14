"""Presence + typing indicators.

Presence model:
- Each connected user writes `presence:user:{id} = 1 EX 60` and refreshes it
  every 30s while a socket is open. Existence == online.
- Typing events are short-lived pub/sub broadcasts on a per-room channel.
  We deliberately don't persist them.
"""

import asyncio
import json
from contextlib import suppress

from app.core.redis_client import get_redis

PRESENCE_TTL = 60
PRESENCE_REFRESH = 30
TYPING_CHANNEL = "chat:typing:{room_id}"
PRESENCE_CHANNEL = "presence:events"


def _presence_key(user_id: int) -> str:
    return f"presence:user:{user_id}"


async def mark_online(user_id: int) -> None:
    r = get_redis()
    await r.set(_presence_key(user_id), "1", ex=PRESENCE_TTL)
    await r.publish(PRESENCE_CHANNEL, json.dumps({"user_id": user_id, "online": True}))


async def mark_offline(user_id: int) -> None:
    r = get_redis()
    await r.delete(_presence_key(user_id))
    await r.publish(PRESENCE_CHANNEL, json.dumps({"user_id": user_id, "online": False}))


async def heartbeat_loop(user_id: int, stop_event: asyncio.Event) -> None:
    """Background task that refreshes the presence TTL until the socket closes."""
    r = get_redis()
    while not stop_event.is_set():
        await r.expire(_presence_key(user_id), PRESENCE_TTL)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=PRESENCE_REFRESH)


async def is_online(user_id: int) -> bool:
    return await get_redis().exists(_presence_key(user_id)) == 1


async def online_subset(user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    r = get_redis()
    pipe = r.pipeline()
    for uid in user_ids:
        pipe.exists(_presence_key(uid))
    flags = await pipe.execute()
    return {uid for uid, flag in zip(user_ids, flags) if flag}


async def publish_typing(room_id: int, user_id: int) -> None:
    await get_redis().publish(
        TYPING_CHANNEL.format(room_id=room_id),
        json.dumps({"room_id": room_id, "user_id": user_id}),
    )
