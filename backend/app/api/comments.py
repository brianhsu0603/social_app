from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.kafka_client import publish
from app.models import Comment, Notification, Post, User
from app.schemas.comment import CommentCreate, CommentOut, CommentUpdate
from app.services import notification_push

router = APIRouter(tags=["comments"])


async def _to_comment_out(db: AsyncSession, comment: Comment) -> dict:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "content": comment.content,
        "created_at": comment.created_at,
        "author": await db.get(User, comment.author_id),
    }


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(
    post_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    if not await db.get(Post, post_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    stmt = (
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(Comment.id.asc())
        .limit(min(limit, 200))
    )
    return [await _to_comment_out(db, c) for c in (await db.execute(stmt)).scalars()]


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    post_id: int,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    if not await db.get(Post, post_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    comment = Comment(post_id=post_id, author_id=current.id, content=payload.content)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    post = await db.get(Post, post_id)
    if post and post.author_id != current.id:
        db.add(
            Notification(
                recipient_id=post.author_id,
                actor_id=current.id,
                type="comment",
                post_id=post_id,
            )
        )
        await db.commit()
        await notification_push.push(post.author_id, {"type": "new_notification"})

    try:
        await publish(
            settings.kafka_events_topic,
            {
                "type": "comment.created",
                "comment_id": comment.id,
                "post_id": post_id,
                "author_id": current.id,
            },
            key=str(post_id),
        )
    except Exception:
        pass  # bus down ≠ write failure; the comment is already saved

    return await _to_comment_out(db, comment)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
async def update_comment(
    comment_id: int,
    payload: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comment not found")
    if comment.author_id != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your comment")
    comment.content = payload.content
    await db.commit()
    await db.refresh(comment)
    return await _to_comment_out(db, comment)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comment not found")
    if comment.author_id != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your comment")
    await db.delete(comment)
    await db.commit()
