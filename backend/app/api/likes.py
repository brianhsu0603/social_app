from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Like, Post, User


router = APIRouter(tags=["likes"])


@router.post("/posts/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    if not db.get(Post, post_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "post not found")
    db.add(Like(post_id=post_id, user_id=current.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # already liked — idempotent


@router.delete("/posts/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
def unlike_post(
    post_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    db.execute(delete(Like).where(Like.post_id == post_id, Like.user_id == current.id))
    db.commit()


@router.get("/posts/{post_id}/likes/count")
def like_count(post_id: int, db: Session = Depends(get_db)) -> dict:
    n = db.scalar(select(func.count(Like.id)).where(Like.post_id == post_id)) or 0
    return {"post_id": post_id, "count": n}
