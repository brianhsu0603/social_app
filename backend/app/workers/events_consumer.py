"""Consumes `social.events` and turns events into side effects:
- push notifications to friends / mentions / recipients
- search index updates (via search_service)
- a stub for analytics fan-out

Designed to scale horizontally: every replica joins the same Kafka
consumer group so partitions get balanced across pods."""

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.kafka_client import consume_with_dlq
from app.models import Comment, Friendship, FriendshipStatus, Post, User
from app.services import push_service, search_service

log = logging.getLogger(__name__)


async def _on_post_created(event: dict) -> None:
    async with AsyncSessionLocal() as db:
        author = await db.get(User, event["author_id"])
        post = await db.get(Post, event["post_id"])
        if not (author and post):
            return
        friend_ids = await _friend_ids(db, author.id)
        if friend_ids:
            await push_service.deliver(
                db,
                friend_ids,
                title=f"{author.display_name} posted",
                body=(post.content or "Tap to see")[:140],
                data={"post_id": str(post.id)},
            )
        search_service.index_post(post, author)


async def _on_comment_created(event: dict) -> None:
    async with AsyncSessionLocal() as db:
        comment = await db.get(Comment, event["comment_id"])
        if not comment:
            return
        post = await db.get(Post, comment.post_id)
        if not post or post.author_id == comment.author_id:
            return
        commenter = await db.get(User, comment.author_id)
        await push_service.deliver(
            db,
            [post.author_id],
            title=f"{commenter.display_name} commented",
            body=comment.content[:140],
            data={"post_id": str(post.id)},
        )


async def _on_friend_accepted(event: dict) -> None:
    async with AsyncSessionLocal() as db:
        a, b = event["a"], event["b"]
        for src, dst in ((a, b), (b, a)):
            src_user = await db.get(User, src)
            if src_user:
                await push_service.deliver(
                    db,
                    [dst],
                    title="New friend",
                    body=f"You are now friends with {src_user.display_name}",
                    data={"user_id": str(src)},
                )


async def _on_user_updated(event: dict) -> None:
    async with AsyncSessionLocal() as db:
        u = await db.get(User, event["user_id"])
        if u:
            search_service.index_user(u)


HANDLERS = {
    "post.created": _on_post_created,
    "comment.created": _on_comment_created,
    "friend.accepted": _on_friend_accepted,
    "user.updated": _on_user_updated,
}


async def _friend_ids(db, user_id: int) -> list[int]:
    rows = (
        await db.execute(
            select(Friendship).where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                (Friendship.requester_id == user_id)
                | (Friendship.addressee_id == user_id),
            )
        )
    ).scalars()
    return [
        f.addressee_id if f.requester_id == user_id else f.requester_id for f in rows
    ]


async def _handle(msg: dict) -> None:
    handler = HANDLERS.get(msg.get("type"))
    if handler is None:
        log.debug("ignoring event type=%s", msg.get("type"))
        return
    await handler(msg)


async def main() -> None:
    stop = asyncio.Event()
    await consume_with_dlq(
        topic=settings.kafka_events_topic,
        group_id=f"{settings.kafka_consumer_group}-events",
        handler=_handle,
        dlq_topic=f"{settings.kafka_events_topic}.dlq",
        stop_event=stop,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
