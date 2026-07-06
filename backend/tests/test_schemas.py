import pytest
from app.schemas.auth import RegisterIn
from app.schemas.post import MediaIn, PostCreate
from pydantic import ValidationError


def test_register_validation() -> None:
    r = RegisterIn(
        email="a@b.com", username="alice", display_name="Alice", password="longenough"
    )
    assert r.username == "alice"

    with pytest.raises(ValidationError):
        RegisterIn(
            email="a@b.com", username="alice", display_name="Alice", password="short"
        )

    with pytest.raises(ValidationError):
        RegisterIn(
            email="not-an-email",
            username="alice",
            display_name="Alice",
            password="longenough",
        )


def test_post_media_type() -> None:
    PostCreate(content="hi", media=[MediaIn(url="http://x/y.png", media_type="image")])
    with pytest.raises(ValidationError):
        MediaIn(url="http://x", media_type="audio")
