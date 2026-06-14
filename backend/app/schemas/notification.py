from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserPublic


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    post_id: int
    read: bool
    created_at: datetime
    actor: UserPublic


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
