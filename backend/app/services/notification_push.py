"""Push real-time events to a specific user via Redis pub/sub."""

import json
import logging

from app.core.redis_client import get_redis

log = logging.getLogger(__name__)

USER_PUSH_CHANNEL = "user:{user_id}:push"


async def push(user_id: int, payload: dict) -> None:
    try:
        await get_redis().publish(
            USER_PUSH_CHANNEL.format(user_id=user_id),
            json.dumps(payload),
        )
    except Exception:
        log.warning("push failed for user_id=%s", user_id)
