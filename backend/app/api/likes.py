from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Like, Notification, Post, User
from app.services import notification_push

router = APIRouter(tags=["likes"])


@router.post("/posts/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def like_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    db.add(Like(post_id=post_id, user_id=current.id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # already liked — idempotent
        return

    if post.author_id != current.id:
        db.add(
            Notification(
                recipient_id=post.author_id,
                actor_id=current.id,
                type="like",
                post_id=post_id,
            )
        )
        await db.commit()
        await notification_push.push(post.author_id, {"type": "new_notification"})


@router.delete("/posts/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    await db.execute(
        delete(Like).where(Like.post_id == post_id, Like.user_id == current.id)
    )
    await db.commit()


@router.get("/posts/{post_id}/likes/count")
async def like_count(post_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    n = (
        await db.scalar(select(func.count(Like.id)).where(Like.post_id == post_id))
    ) or 0
    return {"post_id": post_id, "count": n}
