from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserPublic


class FriendRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requester: UserPublic
    addressee: UserPublic
    status: str
    created_at: datetime
