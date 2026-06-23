from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import chat_service, read_receipt_service
from app.services.ws_manager import manager

router = APIRouter(tags=["chat"])


@router.post("/chat/rooms/{room_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_room_read(
    room_id: int,
    message_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    if not chat_service.is_member(db, room_id, current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member")
    await read_receipt_service.mark_read(room_id, current.id, message_id)
    await manager.broadcast(
        room_id,
        {
            "type": "read_receipt",
            "user_id": current.id,
            "last_read_message_id": message_id,
        },
    )


@router.get("/chat/rooms/{room_id}/receipts")
async def list_receipts(
    room_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict]:
    if not chat_service.is_member(db, room_id, current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member")
    return await read_receipt_service.receipts_for_room(room_id)


@router.get("/chat/rooms/{room_id}/unread")
async def unread(
    room_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    if not chat_service.is_member(db, room_id, current.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member")
    return {
        "room_id": room_id,
        "unread": await read_receipt_service.unread_count(room_id, current.id),
    }
