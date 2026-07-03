import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_post(client, content="Hello world", media=None):
    r = await client.post("/posts", json={"content": content, "media": media or []})
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# POST /posts
# ---------------------------------------------------------------------------


class TestCreatePost:
    async def test_returns_201_with_correct_fields(self, client):
        r = await client.post("/posts", json={"content": "My first post", "media": []})
        assert r.status_code == 201
        data = r.json()
        assert data["content"] == "My first post"
        assert data["like_count"] == 0
        assert data["comment_count"] == 0
        assert data["liked_by_me"] is False
        assert data["author"]["username"] == "alice"

    async def test_creates_post_with_media_attachments(self, client):
        r = await client.post(
            "/posts",
            json={
                "content": "Photo post",
                "media": [{"url": "http://example.com/img.jpg", "media_type": "image"}],
            },
        )
        assert r.status_code == 201
        media = r.json()["media"]
        assert len(media) == 1
        assert media[0]["url"] == "http://example.com/img.jpg"
        assert media[0]["media_type"] == "image"
        assert media[0]["position"] == 0

    async def test_media_positions_assigned_in_order(self, client):
        r = await client.post(
            "/posts",
            json={
                "content": "",
                "media": [
                    {"url": "http://example.com/a.jpg", "media_type": "image"},
                    {"url": "http://example.com/b.mp4", "media_type": "video"},
                ],
            },
        )
        media = r.json()["media"]
        assert [m["position"] for m in media] == [0, 1]

    async def test_empty_content_is_allowed(self, client):
        r = await client.post("/posts", json={"content": "", "media": []})
        assert r.status_code == 201

    async def test_content_exceeding_max_length_rejected(self, client):
        r = await client.post("/posts", json={"content": "x" * 5001, "media": []})
        assert r.status_code == 422

    async def test_invalid_media_type_rejected(self, client):
        r = await client.post(
            "/posts",
            json={
                "content": "bad",
                "media": [{"url": "http://example.com/f.gif", "media_type": "gif"}],
            },
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /posts/{post_id}
# ---------------------------------------------------------------------------


class TestGetPost:
    async def test_returns_post_by_id(self, client):
        post = await _create_post(client, "Test content")
        r = await client.get(f"/posts/{post['id']}")
        assert r.status_code == 200
        assert r.json()["content"] == "Test content"

    async def test_returns_404_for_missing_post(self, client):
        r = await client.get("/posts/99999")
        assert r.status_code == 404

    async def test_like_count_reflects_existing_likes(self, db, client, user_a):
        from app.models import Like

        post = await _create_post(client, "Liked post")
        db.add(Like(post_id=post["id"], user_id=user_a.id))
        await db.commit()
        r = await client.get(f"/posts/{post['id']}")
        assert r.json()["like_count"] == 1
        assert r.json()["liked_by_me"] is True

    async def test_comment_count_reflects_existing_comments(self, db, client, user_a):
        from app.models import Comment

        post = await _create_post(client, "Commented post")
        db.add(Comment(post_id=post["id"], author_id=user_a.id, content="hi"))
        await db.commit()
        r = await client.get(f"/posts/{post['id']}")
        assert r.json()["comment_count"] == 1

    async def test_liked_by_me_false_for_other_users_like(
        self, db, make_client, user_a, user_b
    ):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        await client_b.post(f"/posts/{post['id']}/like")
        r = await client_a.get(f"/posts/{post['id']}")
        assert r.json()["liked_by_me"] is False


# ---------------------------------------------------------------------------
# PATCH /posts/{post_id}
# ---------------------------------------------------------------------------


class TestUpdatePost:
    async def test_author_can_update_content(self, client):
        post = await _create_post(client, "Original")
        r = await client.patch(f"/posts/{post['id']}", json={"content": "Updated"})
        assert r.status_code == 200
        assert r.json()["content"] == "Updated"

    async def test_returns_404_for_missing_post(self, client):
        r = await client.patch("/posts/99999", json={"content": "x"})
        assert r.status_code == 404

    async def test_non_author_gets_403(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        r = await client_b.patch(f"/posts/{post['id']}", json={"content": "hacked"})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /posts/{post_id}
# ---------------------------------------------------------------------------


class TestDeletePost:
    async def test_author_can_delete_post(self, client):
        post = await _create_post(client)
        r = await client.delete(f"/posts/{post['id']}")
        assert r.status_code == 204
        assert (await client.get(f"/posts/{post['id']}")).status_code == 404

    async def test_returns_404_for_missing_post(self, client):
        r = await client.delete("/posts/99999")
        assert r.status_code == 404

    async def test_non_author_gets_403(self, make_client, user_a, user_b):
        client_a = make_client(user_a)
        client_b = make_client(user_b)
        post = await _create_post(client_a)
        r = await client_b.delete(f"/posts/{post['id']}")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /posts/user/{user_id}
# ---------------------------------------------------------------------------


class TestListUserPosts:
    async def test_returns_all_posts_for_user(self, client, user_a):
        await _create_post(client, "Post 1")
        await _create_post(client, "Post 2")
        r = await client.get(f"/posts/user/{user_a.id}")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_returns_empty_list_when_user_has_no_posts(self, client, user_b):
        r = await client.get(f"/posts/user/{user_b.id}")
        assert r.status_code == 200
        assert r.json() == []

    async def test_posts_ordered_newest_first(self, client, user_a):
        await _create_post(client, "First")
        await _create_post(client, "Second")
        r = await client.get(f"/posts/user/{user_a.id}")
        ids = [p["id"] for p in r.json()]
        assert ids == sorted(ids, reverse=True)

    async def test_respects_limit_parameter(self, client, user_a):
        for i in range(5):
            await _create_post(client, f"Post {i}")
        r = await client.get(f"/posts/user/{user_a.id}?limit=3")
        assert len(r.json()) == 3

    async def test_keyset_pagination_with_before_id(self, client, user_a):
        posts = [await _create_post(client, f"Post {i}") for i in range(4)]
        all_ids = sorted(p["id"] for p in posts)
        pivot = all_ids[2]  # the 3rd post id
        r = await client.get(f"/posts/user/{user_a.id}?before_id={pivot}")
        returned_ids = [p["id"] for p in r.json()]
        assert all(pid < pivot for pid in returned_ids)

    async def test_limit_capped_at_50(self, client, user_a):
        for i in range(55):
            await _create_post(client, f"Post {i}")
        r = await client.get(f"/posts/user/{user_a.id}?limit=100")
        assert len(r.json()) <= 50
