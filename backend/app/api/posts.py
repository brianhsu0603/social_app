import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.kafka_client import publish
from app.models import Comment, Like, Post, PostMedia, User
from app.schemas.post import PostCreate, PostOut, PostUpdate

router = APIRouter(prefix="/posts", tags=["posts"])


async def _to_post_out(db: AsyncSession, post: Post, viewer_id: int) -> dict:
    like_count = (
        await db.scalar(select(func.count(Like.id)).where(Like.post_id == post.id))
    ) or 0
    comment_count = (
        await db.scalar(
            select(func.count(Comment.id)).where(Comment.post_id == post.id)
        )
    ) or 0
    liked = (
        await db.scalar(
            select(Like.id).where(Like.post_id == post.id, Like.user_id == viewer_id)
        )
    ) is not None
    return {
        "id": post.id,
        "content": post.content,
        "created_at": post.created_at,
        "author": await db.get(User, post.author_id),
        "media": list(post.media),
        "like_count": like_count,
        "comment_count": comment_count,
        "liked_by_me": liked,
    }


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    post = Post(author_id=current.id, content=payload.content)
    for i, m in enumerate(payload.media):
        post.media.append(PostMedia(url=m.url, media_type=m.media_type, position=i))
    db.add(post)
    await db.commit()
    await db.refresh(post)

    # Fire-and-forget event for downstream consumers (notifications, fan-out, analytics).
    # Bounded with wait_for: aiokafka's idempotent producer retries retriable errors
    # forever with no attempt cap, so an unhealthy broker can hang this await indefinitely
    # otherwise — defeating the "never fail the write because the bus is down" intent.
    try:
        await asyncio.wait_for(
            publish(
                settings.kafka_events_topic,
                {"type": "post.created", "post_id": post.id, "author_id": current.id},
                key=str(current.id),
            ),
            timeout=5.0,
        )
    except Exception:
        pass

    return {
        "id": post.id,
        "content": post.content,
        "created_at": post.created_at,
        "author": current,
        "media": list(post.media),
        "like_count": 0,
        "comment_count": 0,
        "liked_by_me": False,
    }


@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    post = await db.get(Post, post_id, options=[selectinload(Post.media)])
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    return await _to_post_out(db, post, current.id)


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int,
    payload: PostUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    post = await db.get(Post, post_id, options=[selectinload(Post.media)])
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    if post.author_id != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your post")
    post.content = payload.content
    await db.commit()
    await db.refresh(post)
    return await _to_post_out(db, post, current.id)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    if post.author_id != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your post")
    await db.delete(post)
    await db.commit()


@router.get("/user/{user_id}", response_model=list[PostOut])
async def list_user_posts(
    user_id: int,
    limit: int = 20,
    before_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict]:
    stmt = (
        select(Post)
        .where(Post.author_id == user_id)
        .options(selectinload(Post.media))
        .order_by(Post.id.desc())
        .limit(min(limit, 50))
    )
    if before_id is not None:
        stmt = stmt.where(Post.id < before_id)
    posts = list((await db.execute(stmt)).scalars())
    return [await _to_post_out(db, p, current.id) for p in posts]
