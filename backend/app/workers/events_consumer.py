"""Standalone worker for `social.events` (post.created, friend.accepted, etc.).
Intended to run as its own deployment so notification / fan-out work doesn't
share capacity with the HTTP path."""

import asyncio
import logging

from app.core.config import settings
from app.core.kafka_client import consume


log = logging.getLogger(__name__)


async def _handle(msg: dict) -> None:
    # Hook for downstream side-effects: push notifications, email,
    # search indexing, analytics, feed fan-out, etc. Left as a stub.
    log.info("event received: %s", msg)


async def main() -> None:
    stop = asyncio.Event()
    await consume(settings.kafka_events_topic, f"{settings.kafka_consumer_group}-events", _handle, stop)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
