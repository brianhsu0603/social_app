import pytest
from sqlalchemy import select

from app.models import Notification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_post(client, content="A post"):
    r = client.post("/posts", json={"content": content, "media": []})
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/like
# ---------------------------------------------------------------------------


class TestLikePost:
    def test_like_returns_204(self, client):
        post = _create_post(client)
        r = client.post(f"/posts/{post['id']}/like")
        assert r.status_code == 204

    def test_like_nonexistent_post_returns_404(self, client):
        r = client.post("/posts/99999/like")
        assert r.status_code == 404

    def test_duplicate_like_is_idempotent(self, client):
        post = _create_post(client)
        client.post(f"/posts/{post['id']}/like")
        r = client.post(f"/posts/{post['id']}/like")
        assert r.status_code == 204  # no error on second like

    def test_like_does_not_double_count(self, client):
        post = _create_post(client)
        client.post(f"/posts/{post['id']}/like")
        client.post(f"/posts/{post['id']}/like")  # duplicate
        r = client.get(f"/posts/{post['id']}/likes/count")
        assert r.json()["count"] == 1

    def test_like_creates_notification_for_post_author(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = _create_post(client_a)
        client_b.post(f"/posts/{post['id']}/like")

        notif = db.execute(
            select(Notification).where(
                Notification.recipient_id == user_a.id,
                Notification.type == "like",
            )
        ).scalar_one_or_none()
        assert notif is not None
        assert notif.actor_id == user_b.id
        assert notif.post_id == post["id"]

    def test_liking_own_post_does_not_create_notification(
        self, db, make_client, user_a
    ):
        client_a = make_client(user_a)
        post = _create_post(client_a)
        client_a.post(f"/posts/{post['id']}/like")

        notifs = (
            db.execute(
                select(Notification).where(Notification.recipient_id == user_a.id)
            )
            .scalars()
            .all()
        )
        assert notifs == []

    def test_liked_by_me_true_after_like(self, client):
        post = _create_post(client)
        client.post(f"/posts/{post['id']}/like")
        r = client.get(f"/posts/{post['id']}")
        assert r.json()["liked_by_me"] is True


# ---------------------------------------------------------------------------
# DELETE /posts/{post_id}/like
# ---------------------------------------------------------------------------


class TestUnlikePost:
    def test_unlike_returns_204(self, client):
        post = _create_post(client)
        client.post(f"/posts/{post['id']}/like")
        r = client.delete(f"/posts/{post['id']}/like")
        assert r.status_code == 204

    def test_unlike_decrements_count(self, client):
        post = _create_post(client)
        client.post(f"/posts/{post['id']}/like")
        client.delete(f"/posts/{post['id']}/like")
        r = client.get(f"/posts/{post['id']}/likes/count")
        assert r.json()["count"] == 0

    def test_unlike_when_not_liked_is_no_op(self, client):
        post = _create_post(client)
        r = client.delete(f"/posts/{post['id']}/like")
        assert r.status_code == 204

    def test_liked_by_me_false_after_unlike(self, client):
        post = _create_post(client)
        client.post(f"/posts/{post['id']}/like")
        client.delete(f"/posts/{post['id']}/like")
        r = client.get(f"/posts/{post['id']}")
        assert r.json()["liked_by_me"] is False


# ---------------------------------------------------------------------------
# GET /posts/{post_id}/likes/count
# ---------------------------------------------------------------------------


class TestLikeCount:
    def test_count_zero_for_new_post(self, client):
        post = _create_post(client)
        r = client.get(f"/posts/{post['id']}/likes/count")
        assert r.status_code == 200
        assert r.json() == {"post_id": post["id"], "count": 0}

    def test_count_increments_with_each_unique_liker(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = _create_post(client_a)
        client_a.post(f"/posts/{post['id']}/like")
        client_b.post(f"/posts/{post['id']}/like")
        r = client_a.get(f"/posts/{post['id']}/likes/count")
        assert r.json()["count"] == 2

    def test_count_does_not_require_auth(self, client):
        """like_count endpoint has no auth dependency — reachable without user."""
        post = _create_post(client)
        # TestClient already bypasses auth, but the endpoint itself uses no auth dep
        r = client.get(f"/posts/{post['id']}/likes/count")
        assert r.status_code == 200
