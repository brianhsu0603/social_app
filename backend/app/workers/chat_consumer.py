"""In-process Kafka consumer started at app boot. Receives chat messages
fanned out from any backend pod and pushes them to local WebSocket clients."""

import asyncio
import logging

from app.core.config import settings
from app.core.kafka_client import consume
from app.services.ws_manager import manager


log = logging.getLogger(__name__)


async def _handle(msg: dict) -> None:
    room_id = msg.get("room_id")
    if room_id is None:
        return
    await manager.broadcast(int(room_id), msg)


async def run(stop_event: asyncio.Event) -> None:
    # Each backend pod is its own consumer with a unique group suffix, so every
    # pod receives every chat message and can fan it out to its local sockets.
    import socket
    group = f"{settings.kafka_consumer_group}-ws-{socket.gethostname()}"
    log.info("starting chat consumer group=%s", group)
    await consume(settings.kafka_chat_topic, group, _handle, stop_event)
