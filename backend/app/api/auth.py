from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import RegisterIn
from app.schemas.user import UserOut
from app.services import token_service

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenPair:
    user = User(
        email=payload.email.lower(),
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email or username already taken")
    await db.refresh(user)
    access, refresh = await token_service.issue(
        db, user.id, request.headers.get("user-agent")
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Accepts email-or-username in the OAuth2 `username` field."""
    identifier = form.username.lower()
    stmt = select(User).where(
        or_(User.email == identifier, User.username == form.username)
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    access, refresh = await token_service.issue(
        db, user.id, request.headers.get("user-agent")
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> TokenPair:
    pair = await token_service.rotate(db, payload.refresh_token)
    if not pair:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    access, new_refresh = pair
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshIn, db: AsyncSession = Depends(get_db)) -> None:
    await token_service.revoke(db, payload.refresh_token)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current
