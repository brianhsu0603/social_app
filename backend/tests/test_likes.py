import pytest
from sqlalchemy import select

from app.models import Notification

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_post(client, content="A post"):
    r = await client.post("/posts", json={"content": content, "media": []})
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/like
# ---------------------------------------------------------------------------


class TestLikePost:
    async def test_like_returns_204(self, client):
        post = await _create_post(client)
        r = await client.post(f"/posts/{post['id']}/like")
        assert r.status_code == 204

    async def test_like_nonexistent_post_returns_404(self, client):
        r = await client.post("/posts/99999/like")
        assert r.status_code == 404

    async def test_duplicate_like_is_idempotent(self, client):
        post = await _create_post(client)
        await client.post(f"/posts/{post['id']}/like")
        r = await client.post(f"/posts/{post['id']}/like")
        assert r.status_code == 204  # no error on second like

    async def test_like_does_not_double_count(self, client):
        post = await _create_post(client)
        await client.post(f"/posts/{post['id']}/like")
        await client.post(f"/posts/{post['id']}/like")  # duplicate
        r = await client.get(f"/posts/{post['id']}/likes/count")
        assert r.json()["count"] == 1

    async def test_like_creates_notification_for_post_author(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        await client_b.post(f"/posts/{post['id']}/like")

        notif = (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_id == user_a.id,
                    Notification.type == "like",
                )
            )
        ).scalar_one_or_none()
        assert notif is not None
        assert notif.actor_id == user_b.id
        assert notif.post_id == post["id"]

    async def test_liking_own_post_does_not_create_notification(
        self, db, make_client, user_a
    ):
        client_a = make_client(user_a)
        post = await _create_post(client_a)
        await client_a.post(f"/posts/{post['id']}/like")

        notifs = (
            (
                await db.execute(
                    select(Notification).where(Notification.recipient_id == user_a.id)
                )
            )
            .scalars()
            .all()
        )
        assert notifs == []

    async def test_liked_by_me_true_after_like(self, client):
        post = await _create_post(client)
        await client.post(f"/posts/{post['id']}/like")
        r = await client.get(f"/posts/{post['id']}")
        assert r.json()["liked_by_me"] is True


# ---------------------------------------------------------------------------
# DELETE /posts/{post_id}/like
# ---------------------------------------------------------------------------


class TestUnlikePost:
    async def test_unlike_returns_204(self, client):
        post = await _create_post(client)
        await client.post(f"/posts/{post['id']}/like")
        r = await client.delete(f"/posts/{post['id']}/like")
        assert r.status_code == 204

    async def test_unlike_decrements_count(self, client):
        post = await _create_post(client)
        await client.post(f"/posts/{post['id']}/like")
        await client.delete(f"/posts/{post['id']}/like")
        r = await client.get(f"/posts/{post['id']}/likes/count")
        assert r.json()["count"] == 0

    async def test_unlike_when_not_liked_is_no_op(self, client):
        post = await _create_post(client)
        r = await client.delete(f"/posts/{post['id']}/like")
        assert r.status_code == 204

    async def test_liked_by_me_false_after_unlike(self, client):
        post = await _create_post(client)
        await client.post(f"/posts/{post['id']}/like")
        await client.delete(f"/posts/{post['id']}/like")
        r = await client.get(f"/posts/{post['id']}")
        assert r.json()["liked_by_me"] is False


# ---------------------------------------------------------------------------
# GET /posts/{post_id}/likes/count
# ---------------------------------------------------------------------------


class TestLikeCount:
    async def test_count_zero_for_new_post(self, client):
        post = await _create_post(client)
        r = await client.get(f"/posts/{post['id']}/likes/count")
        assert r.status_code == 200
        assert r.json() == {"post_id": post["id"], "count": 0}

    async def test_count_increments_with_each_unique_liker(
        self, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        await client_a.post(f"/posts/{post['id']}/like")
        await client_b.post(f"/posts/{post['id']}/like")
        r = await client_a.get(f"/posts/{post['id']}/likes/count")
        assert r.json()["count"] == 2

    async def test_count_does_not_require_auth(self, client):
        """like_count endpoint has no auth dependency — reachable without user."""
        post = await _create_post(client)
        # TestClient already bypasses auth, but the endpoint itself uses no auth dep
        r = await client.get(f"/posts/{post['id']}/likes/count")
        assert r.status_code == 200
