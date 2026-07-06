from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.kafka_client import publish
from app.models import Friendship, FriendshipStatus, User
from app.schemas.friend import FriendRequestOut
from app.schemas.user import UserPublic
from app.services.feed_service import get_friend_ids, invalidate_friend_cache

router = APIRouter(prefix="/friends", tags=["friends"])


async def _to_friendship_out(db: AsyncSession, f: Friendship) -> dict:
    return {
        "id": f.id,
        "requester": await db.get(User, f.requester_id),
        "addressee": await db.get(User, f.addressee_id),
        "status": f.status.value,
        "created_at": f.created_at,
    }


@router.post(
    "/requests/{user_id}",
    response_model=FriendRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_request(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    if user_id == current.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot friend yourself")
    if not await db.get(User, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    # If they already sent us a request, auto-accept rather than creating a duplicate row.
    inbound = (
        await db.execute(
            select(Friendship).where(
                Friendship.requester_id == user_id,
                Friendship.addressee_id == current.id,
            )
        )
    ).scalar_one_or_none()
    if inbound:
        inbound.status = FriendshipStatus.ACCEPTED
        await db.commit()
        await invalidate_friend_cache(current.id, user_id)
        return await _to_friendship_out(db, inbound)

    f = Friendship(requester_id=current.id, addressee_id=user_id)
    db.add(f)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "request already exists")
    await db.refresh(f)
    return await _to_friendship_out(db, f)


@router.post("/requests/{request_id}/accept", response_model=FriendRequestOut)
async def accept_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    f = await db.get(Friendship, request_id)
    if not f or f.addressee_id != current.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request not found")
    if f.status != FriendshipStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"already {f.status.value}")
    f.status = FriendshipStatus.ACCEPTED
    await db.commit()
    await invalidate_friend_cache(f.requester_id, f.addressee_id)
    try:
        await publish(
            settings.kafka_events_topic,
            {"type": "friend.accepted", "a": f.requester_id, "b": f.addressee_id},
            key=str(f.requester_id),
        )
    except Exception:
        pass
    return await _to_friendship_out(db, f)


@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reject_or_cancel(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    f = await db.get(Friendship, request_id)
    if not f:
        return  # idempotent
    if current.id not in (f.requester_id, f.addressee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your request")
    requester, addressee = f.requester_id, f.addressee_id
    await db.delete(f)
    await db.commit()
    await invalidate_friend_cache(requester, addressee)


@router.get("/requests/incoming", response_model=list[FriendRequestOut])
async def incoming_requests(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict]:
    stmt = select(Friendship).where(
        Friendship.addressee_id == current.id,
        Friendship.status == FriendshipStatus.PENDING,
    )
    return [await _to_friendship_out(db, f) for f in (await db.execute(stmt)).scalars()]


@router.get("", response_model=list[UserPublic])
async def list_friends(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[User]:
    ids = await get_friend_ids(db, current.id)
    if not ids:
        return []
    return list((await db.execute(select(User).where(User.id.in_(ids)))).scalars())
