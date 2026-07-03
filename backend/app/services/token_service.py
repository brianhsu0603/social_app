"""Refresh-token issuance, validation, and rotation with replay detection.

If a refresh token is presented after it has already been rotated, we treat
that as a sign of compromise: revoke every active session for that user and
force them to log in again."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import RefreshToken

REFRESH_TTL_DAYS = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue(
    db: AsyncSession, user_id: int, user_agent: str | None = None
) -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS),
            user_agent=user_agent,
        )
    )
    await db.commit()
    return create_access_token(user_id), raw


async def rotate(db: AsyncSession, presented: str) -> tuple[str, str] | None:
    row = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == _hash(presented))
        )
    ).scalar_one_or_none()
    if not row:
        return None
    if row.expires_at < datetime.now(timezone.utc):
        return None

    if row.revoked or row.rotated_to is not None:
        # Replay of an already-rotated token → revoke entire session family.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id)
            .values(revoked=True)
        )
        await db.commit()
        return None

    access_token, new_refresh = await issue(db, row.user_id, row.user_agent)
    row.revoked = True
    row.rotated_to = _hash(new_refresh)
    await db.commit()
    return access_token, new_refresh


async def revoke(db: AsyncSession, presented: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == _hash(presented))
        .values(revoked=True)
    )
    await db.commit()
