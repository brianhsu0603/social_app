from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserPublic


class MediaIn(BaseModel):
    url: str
    media_type: str = Field(pattern=r"^(image|video)$")


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    media_type: str
    position: int


class PostCreate(BaseModel):
    content: str = Field(default="", max_length=5000)
    media: list[MediaIn] = Field(default_factory=list)


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    author: UserPublic
    media: list[MediaOut]
    like_count: int = 0
    comment_count: int = 0
    liked_by_me: bool = False
