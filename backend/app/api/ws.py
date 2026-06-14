"""User-level WebSocket endpoint.

One connection per logged-in user (not per room). Used to push real-time
events that are not scoped to a single chat room:
  - new_notification   → recipient's unread badge increments
  - new_chat_message   → sender's other open tabs / nav badge increments

Cross-pod delivery reuses the same Redis pub/sub pattern as typing indicators.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from app.api.deps import user_from_token
from app.core.database import SessionLocal
from app.core.redis_client import get_redis
from app.models import Notification
from app.services.notification_push import USER_PUSH_CHANNEL

log = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])


@router.websocket("/ws/user")
async def user_ws(websocket: WebSocket, token: str) -> None:
    db = SessionLocal()
    try:
        user = user_from_token(token, db)
        if not user:
            await websocket.close(code=4401)
            return
        user_id = user.id
        notification_unread = db.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_id == user_id,
                Notification.read.is_(False),
            )
        ) or 0
    finally:
        db.close()

    await websocket.accept()
    await websocket.send_json({"type": "init", "notification_unread": notification_unread})

    redis = get_redis()
    pubsub = redis.pubsub()
    channel = USER_PUSH_CHANNEL.format(user_id=user_id)
    await pubsub.subscribe(channel)

    stop = asyncio.Event()

    async def _relay() -> None:
        try:
            while not stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    await websocket.send_text(msg["data"])
        except Exception:
            stop.set()

    async def _watch() -> None:
        try:
            while True:
                await websocket.receive_text()
        except (WebSocketDisconnect, Exception):
            stop.set()

    relay = asyncio.create_task(_relay())
    watch = asyncio.create_task(_watch())
    try:
        await asyncio.gather(relay, watch)
    except Exception:
        log.exception("user_ws error user_id=%s", user_id)
    finally:
        stop.set()
        relay.cancel()
        watch.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.close()
