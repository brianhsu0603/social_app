from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models import User
from app.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str = Query(min_length=1, max_length=128),
    limit: int = 20,
    _: User = Depends(get_current_user),
) -> dict:
    return {
        "posts": search_service.search_posts(q, limit),
        "users": search_service.search_users(q, limit),
    }
