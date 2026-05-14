from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.post import PostOut
from app.services.feed_service import fetch_posts, get_friend_ids

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("", response_model=list[PostOut])
async def get_feed(
    limit: int = 20,
    before_id: int | None = None,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict]:
    # Self + friends — Facebook-style timeline
    friend_ids = await get_friend_ids(db, current.id)
    author_ids = list({current.id, *friend_ids})
    return fetch_posts(db, current.id, author_ids, min(limit, 50), before_id)
