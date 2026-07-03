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


async def _add_comment(client, post_id, content="A comment"):
    r = await client.post(f"/posts/{post_id}/comments", json={"content": content})
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# GET /posts/{post_id}/comments
# ---------------------------------------------------------------------------


class TestListComments:
    async def test_returns_empty_list_when_no_comments(self, client):
        post = await _create_post(client)
        r = await client.get(f"/posts/{post['id']}/comments")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_404_for_nonexistent_post(self, client):
        r = await client.get("/posts/99999/comments")
        assert r.status_code == 404

    async def test_returns_comments_in_ascending_order(self, client):
        post = await _create_post(client)
        await _add_comment(client, post["id"], "First")
        await _add_comment(client, post["id"], "Second")
        await _add_comment(client, post["id"], "Third")
        comments = (await client.get(f"/posts/{post['id']}/comments")).json()
        assert [c["content"] for c in comments] == ["First", "Second", "Third"]

    async def test_limit_parameter_capped_at_200(self, db, client, user_a):
        from app.models import Comment, Post

        # Create 205 comments directly in DB to avoid a slow HTTP loop
        post_id = (await _create_post(client))["id"]
        p = await db.get(Post, post_id)
        for i in range(205):
            db.add(Comment(post_id=p.id, author_id=user_a.id, content=f"c{i}"))
        await db.commit()
        # Requesting more than 200 should still only return 200
        r = await client.get(f"/posts/{p.id}/comments?limit=205")
        assert len(r.json()) == 200


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/comments
# ---------------------------------------------------------------------------


class TestAddComment:
    async def test_creates_comment_with_correct_fields(self, client):
        post = await _create_post(client)
        r = await client.post(
            f"/posts/{post['id']}/comments", json={"content": "Nice post!"}
        )
        assert r.status_code == 201
        data = r.json()
        assert data["content"] == "Nice post!"
        assert data["post_id"] == post["id"]
        assert data["author"]["username"] == "alice"

    async def test_returns_404_for_nonexistent_post(self, client):
        r = await client.post("/posts/99999/comments", json={"content": "x"})
        assert r.status_code == 404

    async def test_empty_content_rejected(self, client):
        post = await _create_post(client)
        r = await client.post(
            f"/posts/{post['id']}/comments", json={"content": ""}
        )
        assert r.status_code == 422

    async def test_content_over_2000_chars_rejected(self, client):
        post = await _create_post(client)
        r = await client.post(
            f"/posts/{post['id']}/comments", json={"content": "x" * 2001}
        )
        assert r.status_code == 422

    async def test_comment_on_other_users_post_creates_notification(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        await _add_comment(client_b, post["id"], "Hi there!")

        notif = (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_id == user_a.id,
                    Notification.type == "comment",
                )
            )
        ).scalar_one_or_none()
        assert notif is not None
        assert notif.actor_id == user_b.id
        assert notif.post_id == post["id"]

    async def test_comment_on_own_post_does_not_create_notification(
        self, db, make_client, user_a
    ):
        client_a = make_client(user_a)
        post = await _create_post(client_a)
        await _add_comment(client_a, post["id"], "Self comment")

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


# ---------------------------------------------------------------------------
# PATCH /comments/{comment_id}
# ---------------------------------------------------------------------------


class TestUpdateComment:
    async def test_author_can_update_content(self, client):
        post = await _create_post(client)
        comment = await _add_comment(client, post["id"], "Original")
        r = await client.patch(
            f"/comments/{comment['id']}", json={"content": "Updated"}
        )
        assert r.status_code == 200
        assert r.json()["content"] == "Updated"

    async def test_returns_404_for_nonexistent_comment(self, client):
        r = await client.patch("/comments/99999", json={"content": "x"})
        assert r.status_code == 404

    async def test_non_author_gets_403(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        comment = await _add_comment(client_a, post["id"], "Alice's comment")
        r = await client_b.patch(
            f"/comments/{comment['id']}", json={"content": "hacked"}
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /comments/{comment_id}
# ---------------------------------------------------------------------------


class TestDeleteComment:
    async def test_author_can_delete_comment(self, client):
        post = await _create_post(client)
        comment = await _add_comment(client, post["id"], "To delete")
        r = await client.delete(f"/comments/{comment['id']}")
        assert r.status_code == 204

    async def test_returns_404_for_nonexistent_comment(self, client):
        r = await client.delete("/comments/99999")
        assert r.status_code == 404

    async def test_non_author_gets_403(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        comment = await _add_comment(client_a, post["id"], "Mine")
        r = await client_b.delete(f"/comments/{comment['id']}")
        assert r.status_code == 403

    async def test_deleted_comment_no_longer_in_list(self, client):
        post = await _create_post(client)
        comment = await _add_comment(client, post["id"], "Temporary")
        await client.delete(f"/comments/{comment['id']}")
        remaining = (await client.get(f"/posts/{post['id']}/comments")).json()
        assert all(c["id"] != comment["id"] for c in remaining)
