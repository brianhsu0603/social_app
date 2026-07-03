from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.user import UserOut, UserPublic, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=list[UserPublic])
async def search_users(
    q: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[User]:
    pattern = f"%{q}%"
    stmt = (
        select(User)
        .where(or_(User.username.ilike(pattern), User.display_name.ilike(pattern)))
        .limit(min(limit, 50))
    )
    return list((await db.execute(stmt)).scalars())


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current, field, value)
    await db.commit()
    await db.refresh(current)
    return current
