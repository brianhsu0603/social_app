"""Per-(room, user) cursor tracking the last message they've seen.

Stored in Mongo as a separate collection so writes don't contend with the
hot `messages` collection. We use an upsert keyed by (room_id, user_id) so
the document is effectively a single row per pair.
"""

from datetime import datetime, timezone

from bson import ObjectId

from app.core.mongo import get_mongo_db

COLLECTION = "reads"


async def mark_read(room_id: int, user_id: int, message_id: str) -> dict:
    mongo = get_mongo_db()
    oid = ObjectId(message_id)
    now = datetime.now(timezone.utc)
    await mongo[COLLECTION].update_one(
        {"room_id": room_id, "user_id": user_id},
        {
            "$set": {"last_read_message_id": oid, "updated_at": now},
            "$max": {"high_water_mark": oid},  # never go backwards
        },
        upsert=True,
    )
    return {"room_id": room_id, "user_id": user_id, "last_read_message_id": message_id}


async def receipts_for_room(room_id: int) -> list[dict]:
    cursor = get_mongo_db()[COLLECTION].find({"room_id": room_id})
    return [
        {
            "user_id": d["user_id"],
            "last_read_message_id": str(d["last_read_message_id"]),
            "updated_at": d.get("updated_at"),
        }
        async for d in cursor
    ]


async def unread_count(room_id: int, user_id: int) -> int:
    mongo = get_mongo_db()
    cursor_doc = await mongo[COLLECTION].find_one(
        {"room_id": room_id, "user_id": user_id}
    )
    after = cursor_doc["high_water_mark"] if cursor_doc else None
    query: dict = {"room_id": room_id, "sender_id": {"$ne": user_id}}
    if after:
        query["_id"] = {"$gt": after}
    return await mongo["messages"].count_documents(query)


async def ensure_indexes() -> None:
    await get_mongo_db()[COLLECTION].create_index(
        [("room_id", 1), ("user_id", 1)], unique=True
    )
