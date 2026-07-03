import pytest
from sqlalchemy import select

from app.models import Notification, Post

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_post(db, author):
    p = Post(author_id=author.id, content="test post")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def _make_notification(db, recipient, actor, post, notif_type="like", read=False):
    n = Notification(
        recipient_id=recipient.id,
        actor_id=actor.id,
        type=notif_type,
        post_id=post.id,
        read=read,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


# ---------------------------------------------------------------------------
# GET /notifications
# ---------------------------------------------------------------------------


class TestListNotifications:
    async def test_empty_response_when_no_notifications(self, client):
        r = await client.get("/notifications")
        assert r.status_code == 200
        data = r.json()
        assert data["notifications"] == []
        assert data["unread_count"] == 0

    async def test_returns_notifications_for_current_user(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        await _make_notification(
            db, recipient=user_a, actor=user_b, post=post, notif_type="like"
        )
        r = await client_a.get("/notifications")
        data = r.json()
        assert len(data["notifications"]) == 1
        notif = data["notifications"][0]
        assert notif["type"] == "like"
        assert notif["actor"]["username"] == "bob"
        assert notif["post_id"] == post.id
        assert notif["read"] is False

    async def test_does_not_return_other_users_notifications(
        self, db, make_client, user_a, user_b
    ):
        client_b = make_client(user_b)
        post = await _make_post(db, user_a)
        await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        r = await client_b.get("/notifications")
        assert r.json()["notifications"] == []

    async def test_unread_count_reflects_only_unread(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        await _make_notification(
            db, recipient=user_a, actor=user_b, post=post, read=False
        )
        await _make_notification(
            db, recipient=user_a, actor=user_b, post=post, read=True
        )
        await _make_notification(
            db, recipient=user_a, actor=user_b, post=post, read=False
        )
        r = await client_a.get("/notifications")
        assert r.json()["unread_count"] == 2

    async def test_notifications_ordered_newest_first(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        r = await client_a.get("/notifications")
        ids = [n["id"] for n in r.json()["notifications"]]
        assert ids == sorted(ids, reverse=True)

    async def test_capped_at_50_results(self, db, make_client, user_a, user_b):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        for _ in range(55):
            await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        r = await client_a.get("/notifications")
        assert len(r.json()["notifications"]) == 50


# ---------------------------------------------------------------------------
# PATCH /notifications/{notification_id}/read
# ---------------------------------------------------------------------------


class TestMarkOneRead:
    async def test_marks_notification_as_read(self, db, make_client, user_a, user_b):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        n = await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        assert n.read is False
        r = await client_a.patch(f"/notifications/{n.id}/read")
        assert r.status_code == 204
        await db.refresh(n)
        assert n.read is True

    async def test_nonexistent_notification_silently_ignored(self, client):
        r = await client.patch("/notifications/99999/read")
        assert r.status_code == 204

    async def test_cannot_mark_other_users_notification_read(
        self, db, make_client, user_a, user_b
    ):
        client_b = make_client(user_b)
        post = await _make_post(db, user_a)
        n = await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        r = await client_b.patch(f"/notifications/{n.id}/read")
        assert r.status_code == 204  # silently ignored
        await db.refresh(n)
        assert (
            n.read is False
        )  # ownership check: user_b can't read user_a's notification

    async def test_already_read_notification_stays_read(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        n = await _make_notification(
            db, recipient=user_a, actor=user_b, post=post, read=True
        )
        r = await client_a.patch(f"/notifications/{n.id}/read")
        assert r.status_code == 204
        await db.refresh(n)
        assert n.read is True


# ---------------------------------------------------------------------------
# POST /notifications/read-all
# ---------------------------------------------------------------------------


class TestMarkAllRead:
    async def test_marks_all_notifications_read(self, db, make_client, user_a, user_b):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        n1 = await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        n2 = await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        r = await client_a.post("/notifications/read-all")
        assert r.status_code == 204
        await db.refresh(n1)
        await db.refresh(n2)
        assert n1.read is True
        assert n2.read is True

    async def test_does_not_affect_other_users_notifications(
        self, db, make_client, user_a, user_b
    ):
        client_b = make_client(user_b)
        post = await _make_post(db, user_a)
        n = await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        await client_b.post("/notifications/read-all")  # user_b marks their own read
        await db.refresh(n)
        assert n.read is False  # user_a's notification untouched

    async def test_unread_count_is_zero_after_mark_all(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        post = await _make_post(db, user_a)
        await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        await _make_notification(db, recipient=user_a, actor=user_b, post=post)
        await client_a.post("/notifications/read-all")
        r = await client_a.get("/notifications")
        assert r.json()["unread_count"] == 0

    async def test_no_op_when_no_notifications(self, client):
        r = await client.post("/notifications/read-all")
        assert r.status_code == 204
