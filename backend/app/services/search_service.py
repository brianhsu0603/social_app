"""Meilisearch indexing + query.

Indexes are mostly write-through: each post/user mutation pushes a doc.
A periodic backfill is left as a future task — for now we rely on the
events worker to keep things in sync."""

import logging
import os
from typing import Any

import httpx

from app.models import Post, User

log = logging.getLogger(__name__)

MEILI_URL = os.getenv("MEILI_URL", "http://meilisearch:7700")
MEILI_KEY = os.getenv("MEILI_MASTER_KEY", "masterKey")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {MEILI_KEY}", "Content-Type": "application/json"}


def _request(method: str, path: str, json: Any | None = None) -> dict | None:
    try:
        r = httpx.request(
            method, f"{MEILI_URL}{path}", headers=_headers(), json=json, timeout=5.0
        )
        if r.status_code >= 400:
            log.warning("meili %s %s -> %s %s", method, path, r.status_code, r.text)
            return None
        return r.json() if r.content else None
    except Exception as e:
        log.warning("meili %s %s failed: %s", method, path, e)
        return None


def ensure_indexes() -> None:
    for index, primary in (("posts", "id"), ("users", "id")):
        _request("POST", "/indexes", {"uid": index, "primaryKey": primary})
    _request(
        "PATCH",
        "/indexes/posts/settings",
        {"searchableAttributes": ["content", "author_name"]},
    )
    _request(
        "PATCH",
        "/indexes/users/settings",
        {"searchableAttributes": ["username", "display_name", "bio"]},
    )


def index_post(post: Post, author: User) -> None:
    _request(
        "POST",
        "/indexes/posts/documents",
        [
            {
                "id": post.id,
                "content": post.content,
                "author_id": author.id,
                "author_name": author.display_name,
                "created_at": post.created_at.isoformat() if post.created_at else None,
            }
        ],
    )


def index_user(user: User) -> None:
    _request(
        "POST",
        "/indexes/users/documents",
        [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "bio": user.bio,
            }
        ],
    )


def remove_post(post_id: int) -> None:
    _request("DELETE", f"/indexes/posts/documents/{post_id}")


def search_posts(q: str, limit: int = 20) -> list[dict]:
    return (
        _request("POST", "/indexes/posts/search", {"q": q, "limit": min(limit, 50)})
        or {}
    ).get("hits") or []


def search_users(q: str, limit: int = 20) -> list[dict]:
    return (
        _request("POST", "/indexes/users/search", {"q": q, "limit": min(limit, 50)})
        or {}
    ).get("hits") or []
