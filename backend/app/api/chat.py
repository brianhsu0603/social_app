import asyncio
import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, user_from_token
from app.core.database import SessionLocal, get_db
from app.core.observability import WS_CONNECTIONS
from app.core.redis_client import get_redis
from app.models import ChatRoom, ChatRoomMember, User
from app.schemas.chat import ChatMessageIn, ChatMessageOut, ChatRoomCreate, ChatRoomOut
from app.services import chat_service, presence_service
from app.services.ws_manager import manager

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


def _room_with_members(db: Session, room: ChatRoom) -> dict:
    member_ids = (
        db.execute(
            select(ChatRoomMember.user_id).where(ChatRoomMember.room_id == room.id)
        )
        .scalars()
        .all()
    )
    members = list(db.execute(select(User).where(User.id.in_(member_ids))).scalars())
    return {
        "id": room.id,
        "name": room.name,
        "is_group": room.is_group,
        "created_by": room.created_by,
        "created_at": room.created_at,
        "members": members,
    }


@router.post("/rooms", response_model=ChatRoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: ChatRoomCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    member_ids = sorted(set(payload.member_ids) | {current.id})
    is_group = len(member_ids) > 2

    if not is_group and len(member_ids) == 2:
        existing = db.execute(
            select(ChatRoom)
            .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
            .where(ChatRoom.is_group.is_(False), ChatRoomMember.user_id.in_(member_ids))
            .group_by(ChatRoom.id)
            .having(func.count(ChatRoomMember.id) == 2)
        ).scalar()
        if existing:
            return _room_with_members(db, existing)

    room = ChatRoom(name=payload.name, is_group=is_group, created_by=current.id)
    db.add(room)
    db.flush()
    for uid in member_ids:
        db.add(ChatRoomMember(room_id=room.id, user_id=uid))
    db.commit()
    db.refresh(room)
    return _room_with_members(db, room)


@router.get("/rooms", response_model=list[ChatRoomOut])
def list_my_rooms(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict]:
    room_ids = (
        db.execute(
            select(ChatRoomMember.room_id).where(ChatRoomMember.user_id == current.id)
        )
        .scalars()
        .all()
    )
    if not room_ids:
        return []
    rooms = list(
        db.execute(select(ChatRoom).where(ChatRoom.id.in_(room_ids))).scalars()
    )
    rooms.sort(key=lambda r: r.id, reverse=True)
    return [_room_with_members(db, r) for r in rooms]


@router.get("/rooms/{room_id}/messages", response_model=list[ChatMessageOut])
async def history(
    room_id: int,
    limit: int = 50,
    before_id: str | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict]:
    if not chat_service.is_member(db, room_id, current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member")
    return await chat_service.list_history(room_id, limit=limit, before_id=before_id)


@router.post(
    "/rooms/{room_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message_rest(
    room_id: int,
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    if payload.room_id != room_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "room_id mismatch")
    if not chat_service.is_member(db, room_id, current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member")
    return await chat_service.persist_and_fan_out(
        room_id=room_id,
        sender_id=current.id,
        content=payload.content,
        media_url=payload.media_url,
        media_type=payload.media_type,
    )


@router.websocket("/ws/{room_id}")
async def chat_ws(websocket: WebSocket, room_id: int, token: str) -> None:
    db = SessionLocal()
    try:
        user = user_from_token(token, db)
        if not user or not chat_service.is_member(db, room_id, user.id):
            await websocket.close(code=4401)
            return
    finally:
        db.close()

    await manager.connect(room_id, websocket)
    WS_CONNECTIONS.labels("chat").inc()
    await presence_service.mark_online(user.id)

    stop_event = asyncio.Event()
    heartbeat = asyncio.create_task(
        presence_service.heartbeat_loop(user.id, stop_event)
    )
    typing_task = asyncio.create_task(_subscribe_typing(room_id, websocket, stop_event))

    try:
        while True:
            payload = await websocket.receive_json()
            kind = payload.get("type", "message")
            if kind == "typing":
                await presence_service.publish_typing(room_id, user.id)
                continue
            await chat_service.persist_and_fan_out(
                room_id=room_id,
                sender_id=user.id,
                content=payload.get("content", ""),
                media_url=payload.get("media_url"),
                media_type=payload.get("media_type"),
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws error")
    finally:
        stop_event.set()
        heartbeat.cancel()
        typing_task.cancel()
        await manager.disconnect(room_id, websocket)
        WS_CONNECTIONS.labels("chat").dec()
        await presence_service.mark_offline(user.id)


async def _subscribe_typing(
    room_id: int, ws: WebSocket, stop_event: asyncio.Event
) -> None:
    """Bridge Redis typing channel → this socket. One pubsub task per socket
    is wasteful at huge scale; for now it keeps the code simple."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(presence_service.TYPING_CHANNEL.format(room_id=room_id))
    try:
        while not stop_event.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                try:
                    payload = json.loads(msg["data"])
                except Exception:
                    continue
                await ws.send_json({"type": "typing", **payload})
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()
