from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


async def user_from_token(token: str, db: AsyncSession) -> User | None:
    """Auth helper for WebSocket connections that pass token as query param."""
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (InvalidTokenError, ValueError, TypeError):
        return None
    return await db.get(User, user_id)
