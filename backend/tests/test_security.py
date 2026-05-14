from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip() -> None:
    h = hash_password("supersecret")
    assert h != "supersecret"
    assert verify_password("supersecret", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip() -> None:
    token = create_access_token(42)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload
