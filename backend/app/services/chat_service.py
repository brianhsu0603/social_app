"""Chat persistence + Kafka fan-out.

Pipeline per message:
  1. WebSocket receives an inbound message from a sender.
  2. We append it to Mongo (`messages` collection) so history is durable.
  3. We publish to Kafka `chat.messages` keyed by room_id (ordering per room).
  4. A consumer in each backend pod reads the topic and pushes to any locally
     connected WebSocket subscribers for that room. This is how the same room
     stays in sync across multiple backend replicas.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.kafka_client import publish
from app.core.mongo import get_mongo_db
from app.models import ChatRoom, ChatRoomMember

COLLECTION = "messages"


def is_member(db: Session, room_id: int, user_id: int) -> bool:
    stmt = select(ChatRoomMember.id).where(
        ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id
    )
    return db.scalar(stmt) is not None


async def persist_and_fan_out(
    *,
    room_id: int,
    sender_id: int,
    content: str,
    media_url: str | None,
    media_type: str | None,
) -> dict[str, Any]:
    doc = {
        "room_id": room_id,
        "sender_id": sender_id,
        "content": content,
        "media_url": media_url,
        "media_type": media_type,
        "created_at": datetime.now(timezone.utc),
    }
    mongo = get_mongo_db()
    result = await mongo[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id

    payload = _serialize(doc)
    await publish(settings.kafka_chat_topic, payload, key=str(room_id))
    return payload


async def list_history(
    room_id: int, limit: int = 50, before_id: str | None = None
) -> list[dict]:
    mongo = get_mongo_db()
    query: dict[str, Any] = {"room_id": room_id}
    if before_id:
        query["_id"] = {"$lt": ObjectId(before_id)}
    cursor = mongo[COLLECTION].find(query).sort("_id", -1).limit(min(limit, 200))
    return [_serialize(doc) async for doc in cursor]


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "room_id": doc["room_id"],
        "sender_id": doc["sender_id"],
        "content": doc.get("content", ""),
        "media_url": doc.get("media_url"),
        "media_type": doc.get("media_type"),
        "created_at": (
            doc["created_at"].isoformat()
            if isinstance(doc["created_at"], datetime)
            else doc["created_at"]
        ),
    }


def ensure_room(db: Session, room_id: int) -> ChatRoom:
    room = db.get(ChatRoom, room_id)
    if not room:
        raise ValueError("room not found")
    return room
