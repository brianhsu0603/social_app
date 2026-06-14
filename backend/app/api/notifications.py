from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Notification, User
from app.schemas.notification import NotificationListOut, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
def list_notifications(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> NotificationListOut:
    rows = db.execute(
        select(Notification)
        .where(Notification.recipient_id == current.id)
        .order_by(Notification.id.desc())
        .limit(50)
    ).scalars().all()

    items = []
    for n in rows:
        actor = db.get(User, n.actor_id)
        if actor:
            items.append(
                NotificationOut(
                    id=n.id,
                    type=n.type,
                    post_id=n.post_id,
                    read=n.read,
                    created_at=n.created_at,
                    actor=actor,
                )
            )

    unread_count = sum(1 for n in rows if not n.read)
    return NotificationListOut(notifications=items, unread_count=unread_count)


@router.patch("/{notification_id}/read", status_code=204)
def mark_one_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    n = db.get(Notification, notification_id)
    if not n or n.recipient_id != current.id:
        return
    n.read = True
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    db.execute(
        update(Notification)
        .where(Notification.recipient_id == current.id, Notification.read == False)
        .values(read=True)
    )
    db.commit()
