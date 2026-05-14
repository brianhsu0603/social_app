from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models import User
from app.services import presence_service

router = APIRouter(prefix="/presence", tags=["presence"])


@router.get("")
async def get_presence(
    user_ids: list[int] = Query(default_factory=list),
    _: User = Depends(get_current_user),
) -> dict[int, bool]:
    online = await presence_service.online_subset(user_ids)
    return {uid: uid in online for uid in user_ids}
