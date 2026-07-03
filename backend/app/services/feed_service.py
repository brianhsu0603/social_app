"""Feed reads. Caches each user's friend-id list in Redis; the post query
itself stays on Postgres for now (good enough until the friend graph or
post volume forces a fan-out cache)."""

import json

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redis_client import get_redis
from app.models import Friendship, FriendshipStatus, Like, Post, Comment

FRIEND_IDS_CACHE_TTL = 60  # seconds


async def get_friend_ids(db: AsyncSession, user_id: int) -> list[int]:
    redis = get_redis()
    cache_key = f"friend_ids:{user_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    stmt = select(
        case(
            (Friendship.requester_id == user_id, Friendship.addressee_id),
            else_=Friendship.requester_id,
        )
    ).where(
        and_(
            Friendship.status == FriendshipStatus.ACCEPTED,
            or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
        )
    )
    ids = [row[0] for row in (await db.execute(stmt)).all()]
    await redis.set(cache_key, json.dumps(ids), ex=FRIEND_IDS_CACHE_TTL)
    return ids


async def invalidate_friend_cache(*user_ids: int) -> None:
    redis = get_redis()
    keys = [f"friend_ids:{uid}" for uid in user_ids]
    if keys:
        await redis.delete(*keys)


async def fetch_posts(
    db: AsyncSession,
    viewer_id: int,
    author_ids: list[int],
    limit: int,
    before_id: int | None,
) -> list[dict]:
    if not author_ids:
        return []

    like_count = (
        select(Like.post_id, func.count(Like.id).label("n"))
        .group_by(Like.post_id)
        .subquery()
    )
    comment_count = (
        select(Comment.post_id, func.count(Comment.id).label("n"))
        .group_by(Comment.post_id)
        .subquery()
    )
    liked_by_me = select(Like.post_id).where(Like.user_id == viewer_id).subquery()

    stmt = (
        select(
            Post,
            func.coalesce(like_count.c.n, 0).label("like_count"),
            func.coalesce(comment_count.c.n, 0).label("comment_count"),
            (liked_by_me.c.post_id.is_not(None)).label("liked_by_me"),
        )
        .outerjoin(like_count, like_count.c.post_id == Post.id)
        .outerjoin(comment_count, comment_count.c.post_id == Post.id)
        .outerjoin(liked_by_me, liked_by_me.c.post_id == Post.id)
        .where(Post.author_id.in_(author_ids))
        .options(selectinload(Post.media))
        .order_by(Post.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(Post.id < before_id)

    rows = (await db.execute(stmt)).all()
    results = []
    # Eager-load authors in one query
    author_ids_seen = {row[0].author_id for row in rows}
    from app.models import User

    authors = {
        u.id: u
        for u in (
            await db.execute(select(User).where(User.id.in_(author_ids_seen)))
        ).scalars()
    }
    for post, lc, cc, lbm in rows:
        results.append(
            {
                "id": post.id,
                "content": post.content,
                "created_at": post.created_at,
                "author": authors[post.author_id],
                "media": list(post.media),
                "like_count": lc,
                "comment_count": cc,
                "liked_by_me": bool(lbm),
            }
        )
    return results
