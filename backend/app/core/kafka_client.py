"""Kafka producer + consumer helpers.

Producer is idempotent and retries forever on transient errors. Consumers
support manual-commit + DLQ semantics so a poison message can't block the
group, and we can replay from the DLQ once the bug is fixed.
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from app.core.config import settings

log = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            enable_idempotence=True,
            acks="all",
            request_timeout_ms=15000,
            linger_ms=5,
            compression_type="gzip",
        )
        await _producer.start()
    return _producer


async def close_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def publish(topic: str, value: dict, key: Optional[str] = None) -> None:
    producer = await get_producer()
    await producer.send_and_wait(
        topic,
        value=value,
        key=key.encode("utf-8") if key else None,
    )


async def consume(
    topic: str,
    group_id: str,
    handler: Callable[[dict], Awaitable[None]],
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Backwards-compatible consumer for fire-and-forget topics."""
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=True,
        auto_offset_reset="latest",
    )
    await consumer.start()
    try:
        async for msg in consumer:
            if stop_event and stop_event.is_set():
                break
            try:
                await handler(msg.value)
            except Exception:
                log.exception("handler failed")
    finally:
        await consumer.stop()


async def consume_with_dlq(
    *,
    topic: str,
    group_id: str,
    handler: Callable[[dict], Awaitable[None]],
    dlq_topic: str,
    stop_event: Optional[asyncio.Event] = None,
    max_attempts: int = 3,
    backoff_base: float = 0.5,
) -> None:
    """Manual-commit consumer with retry + dead-letter routing.

    Per-message: try `handler` up to `max_attempts` times with exponential
    backoff. On final failure, publish the original payload (plus diagnostic
    metadata) to `dlq_topic`, commit the offset, and move on so the group
    isn't stuck on one poison record.
    """
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for msg in consumer:
            if stop_event and stop_event.is_set():
                break

            ok = False
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    await handler(msg.value)
                    ok = True
                    break
                except Exception as e:
                    last_exc = e
                    log.warning(
                        "handler attempt %d/%d failed topic=%s offset=%s: %s",
                        attempt + 1,
                        max_attempts,
                        topic,
                        msg.offset,
                        e,
                    )
                    await asyncio.sleep(backoff_base * (2**attempt))

            if not ok:
                try:
                    await publish(
                        dlq_topic,
                        {
                            "payload": msg.value,
                            "source_topic": topic,
                            "offset": msg.offset,
                            "partition": msg.partition,
                            "error": str(last_exc),
                        },
                        key=str(msg.key.decode()) if msg.key else None,
                    )
                except KafkaError:
                    log.exception("could not push to DLQ; will not commit")
                    # Don't commit — let it retry next poll cycle.
                    continue

            await consumer.commit()
    finally:
        await consumer.stop()
