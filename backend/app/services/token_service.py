"""Refresh-token issuance, validation, and rotation with replay detection.

If a refresh token is presented after it has already been rotated, we treat
that as a sign of compromise: revoke every active session for that user and
force them to log in again."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import RefreshToken

REFRESH_TTL_DAYS = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue(db: Session, user_id: int, user_agent: str | None = None) -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS),
            user_agent=user_agent,
        )
    )
    db.commit()
    return create_access_token(user_id), raw


def rotate(db: Session, presented: str) -> tuple[str, str] | None:
    row = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == _hash(presented))
        .one_or_none()
    )
    if not row:
        return None
    if row.expires_at < datetime.now(timezone.utc):
        return None

    if row.revoked or row.rotated_to is not None:
        # Replay of an already-rotated token → revoke entire session family.
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id)
            .values(revoked=True)
        )
        db.commit()
        return None

    access_token, new_refresh = issue(db, row.user_id, row.user_agent)
    row.revoked = True
    row.rotated_to = _hash(new_refresh)
    db.commit()
    return access_token, new_refresh


def revoke(db: Session, presented: str) -> None:
    db.query(RefreshToken).filter(RefreshToken.token_hash == _hash(presented)).update(
        {"revoked": True}
    )
    db.commit()
