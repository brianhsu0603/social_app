from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Device, User

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceRegister(BaseModel):
    platform: str = Field(pattern=r"^(fcm|apns|web)$")
    token: str = Field(min_length=4, max_length=512)


@router.post("", status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegister,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    # Idempotent: if the token already exists, just reattach it to the caller.
    existing = db.execute(
        select(Device).where(Device.token == payload.token)
    ).scalar_one_or_none()
    if existing:
        existing.user_id = current.id
        existing.platform = payload.platform
        db.commit()
        return {"id": existing.id}

    d = Device(user_id=current.id, platform=payload.platform, token=payload.token)
    db.add(d)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    db.refresh(d)
    return {"id": d.id}


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    token: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    db.query(Device).filter(
        Device.user_id == current.id, Device.token == token
    ).delete()
    db.commit()
