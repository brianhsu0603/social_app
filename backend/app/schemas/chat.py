from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserPublic


class ChatRoomCreate(BaseModel):
    name: str | None = None
    member_ids: list[int] = Field(min_length=1)


class ChatRoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    is_group: bool
    created_by: int
    created_at: datetime
    members: list[UserPublic] = []


class ChatMessageIn(BaseModel):
    room_id: int
    content: str = ""
    media_url: str | None = None
    media_type: str | None = None  # image | video | None


class ChatMessageOut(BaseModel):
    id: str
    room_id: int
    sender_id: int
    content: str
    media_url: str | None = None
    media_type: str | None = None
    created_at: datetime
