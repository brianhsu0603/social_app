from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
def register(
    payload: RegisterIn, request: Request, db: Session = Depends(get_db)
) -> TokenPair:
    user = User(
        email=payload.email.lower(),
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email or username already taken")
    db.refresh(user)
    access, refresh = token_service.issue(
        db, user.id, request.headers.get("user-agent")
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenPair:
    """Accepts email-or-username in the OAuth2 `username` field."""
    identifier = form.username.lower()
    stmt = select(User).where(
        or_(User.email == identifier, User.username == form.username)
    )
    user = db.execute(stmt).scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    access, refresh = token_service.issue(
        db, user.id, request.headers.get("user-agent")
    )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)) -> TokenPair:
    pair = token_service.rotate(db, payload.refresh_token)
    if not pair:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    access, new_refresh = pair
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshIn, db: Session = Depends(get_db)) -> None:
    token_service.revoke(db, payload.refresh_token)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current
