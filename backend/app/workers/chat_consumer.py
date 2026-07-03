"""In-process Kafka consumer started at app boot. Receives chat messages
fanned out from any backend pod and pushes them to local WebSocket clients."""

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.kafka_client import consume
from app.models import ChatRoomMember
from app.services import notification_push
from app.services.ws_manager import manager

log = logging.getLogger(__name__)


async def _handle(msg: dict) -> None:
    room_id = msg.get("room_id")
    if room_id is None:
        return
    await manager.broadcast(int(room_id), msg)

    sender_id = msg.get("sender_id")
    try:
        async with AsyncSessionLocal() as db:
            member_ids = (
                (
                    await db.execute(
                        select(ChatRoomMember.user_id).where(
                            ChatRoomMember.room_id == room_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        for uid in member_ids:
            if uid != sender_id:
                await notification_push.push(
                    uid, {"type": "new_chat_message", "room_id": room_id}
                )
    except Exception:
        log.warning("failed to push chat unread update for room_id=%s", room_id)


async def run(stop_event: asyncio.Event) -> None:
    # Each backend pod is its own consumer with a unique group suffix, so every
    # pod receives every chat message and can fan it out to its local sockets.
    import socket

    group = f"{settings.kafka_consumer_group}-ws-{socket.gethostname()}"
    log.info("starting chat consumer group=%s", group)
    await consume(settings.kafka_chat_topic, group, _handle, stop_event)
