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


def _add_comment(client, post_id, content="A comment"):
    r = client.post(f"/posts/{post_id}/comments", json={"content": content})
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# GET /posts/{post_id}/comments
# ---------------------------------------------------------------------------

class TestListComments:
    def test_returns_empty_list_when_no_comments(self, client):
        post = _create_post(client)
        r = client.get(f"/posts/{post['id']}/comments")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_404_for_nonexistent_post(self, client):
        r = client.get("/posts/99999/comments")
        assert r.status_code == 404

    def test_returns_comments_in_ascending_order(self, client):
        post = _create_post(client)
        _add_comment(client, post["id"], "First")
        _add_comment(client, post["id"], "Second")
        _add_comment(client, post["id"], "Third")
        comments = client.get(f"/posts/{post['id']}/comments").json()
        assert [c["content"] for c in comments] == ["First", "Second", "Third"]

    def test_limit_parameter_capped_at_200(self, db, client, user_a):
        from app.models import Comment, Post
        # Create 205 comments directly in DB to avoid a slow HTTP loop
        p = db.get(Post, _create_post(client)["id"])
        for i in range(205):
            db.add(Comment(post_id=p.id, author_id=user_a.id, content=f"c{i}"))
        db.commit()
        # Requesting more than 200 should still only return 200
        r = client.get(f"/posts/{p.id}/comments?limit=205")
        assert len(r.json()) == 200


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/comments
# ---------------------------------------------------------------------------

class TestAddComment:
    def test_creates_comment_with_correct_fields(self, client):
        post = _create_post(client)
        r = client.post(f"/posts/{post['id']}/comments", json={"content": "Nice post!"})
        assert r.status_code == 201
        data = r.json()
        assert data["content"] == "Nice post!"
        assert data["post_id"] == post["id"]
        assert data["author"]["username"] == "alice"

    def test_returns_404_for_nonexistent_post(self, client):
        r = client.post("/posts/99999/comments", json={"content": "x"})
        assert r.status_code == 404

    def test_empty_content_rejected(self, client):
        post = _create_post(client)
        r = client.post(f"/posts/{post['id']}/comments", json={"content": ""})
        assert r.status_code == 422

    def test_content_over_2000_chars_rejected(self, client):
        post = _create_post(client)
        r = client.post(f"/posts/{post['id']}/comments", json={"content": "x" * 2001})
        assert r.status_code == 422

    def test_comment_on_other_users_post_creates_notification(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = _create_post(client_a)
        _add_comment(client_b, post["id"], "Hi there!")

        notif = db.execute(
            select(Notification).where(
                Notification.recipient_id == user_a.id,
                Notification.type == "comment",
            )
        ).scalar_one_or_none()
        assert notif is not None
        assert notif.actor_id == user_b.id
        assert notif.post_id == post["id"]

    def test_comment_on_own_post_does_not_create_notification(
        self, db, make_client, user_a
    ):
        client_a = make_client(user_a)
        post = _create_post(client_a)
        _add_comment(client_a, post["id"], "Self comment")

        notifs = db.execute(
            select(Notification).where(Notification.recipient_id == user_a.id)
        ).scalars().all()
        assert notifs == []


# ---------------------------------------------------------------------------
# PATCH /comments/{comment_id}
# ---------------------------------------------------------------------------

class TestUpdateComment:
    def test_author_can_update_content(self, client):
        post = _create_post(client)
        comment = _add_comment(client, post["id"], "Original")
        r = client.patch(f"/comments/{comment['id']}", json={"content": "Updated"})
        assert r.status_code == 200
        assert r.json()["content"] == "Updated"

    def test_returns_404_for_nonexistent_comment(self, client):
        r = client.patch("/comments/99999", json={"content": "x"})
        assert r.status_code == 404

    def test_non_author_gets_403(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = _create_post(client_a)
        comment = _add_comment(client_a, post["id"], "Alice's comment")
        r = client_b.patch(f"/comments/{comment['id']}", json={"content": "hacked"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /comments/{comment_id}
# ---------------------------------------------------------------------------

class TestDeleteComment:
    def test_author_can_delete_comment(self, client):
        post = _create_post(client)
        comment = _add_comment(client, post["id"], "To delete")
        r = client.delete(f"/comments/{comment['id']}")
        assert r.status_code == 204

    def test_returns_404_for_nonexistent_comment(self, client):
        r = client.delete("/comments/99999")
        assert r.status_code == 404

    def test_non_author_gets_403(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = _create_post(client_a)
        comment = _add_comment(client_a, post["id"], "Mine")
        r = client_b.delete(f"/comments/{comment['id']}")
        assert r.status_code == 403

    def test_deleted_comment_no_longer_in_list(self, client):
        post = _create_post(client)
        comment = _add_comment(client, post["id"], "Temporary")
        client.delete(f"/comments/{comment['id']}")
        remaining = client.get(f"/posts/{post['id']}/comments").json()
        assert all(c["id"] != comment["id"] for c in remaining)
