from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Device, User

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceRegister(BaseModel):
    platform: str = Field(pattern=r"^(fcm|apns|web)$")
    token: str = Field(min_length=4, max_length=512)


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegister,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict:
    # Idempotent: if the token already exists, just reattach it to the caller.
    existing = (
        await db.execute(select(Device).where(Device.token == payload.token))
    ).scalar_one_or_none()
    if existing:
        existing.user_id = current.id
        existing.platform = payload.platform
        await db.commit()
        return {"id": existing.id}

    d = Device(user_id=current.id, platform=payload.platform, token=payload.token)
    db.add(d)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
    await db.refresh(d)
    return {"id": d.id}


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    token: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    await db.execute(
        delete(Device).where(Device.user_id == current.id, Device.token == token)
    )
    await db.commit()
