import json
import asyncio
from typing import Awaitable, Callable, Optional

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

from app.core.config import settings


_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            enable_idempotence=True,
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
            except Exception as exc:  # don't kill the consumer loop on bad data
                import logging
                logging.exception("kafka handler failed: %s", exc)
    finally:
        await consumer.stop()
