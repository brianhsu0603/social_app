import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user
from app.core.kafka_client import publish
from app.core.minio_client import put_object
from app.models import User

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO = {"video/mp4", "video/webm", "video/quicktime"}
MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50MB


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
) -> dict:
    content_type = file.content_type or ""
    if content_type in ALLOWED_IMAGE:
        media_type = "image"
    elif content_type in ALLOWED_VIDEO:
        media_type = "video"
    else:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported: {content_type}"
        )

    data = await file.read()
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    ext = PurePosixPath(file.filename or "").suffix or ""
    object_name = f"u{current.id}/{uuid.uuid4().hex}{ext}"
    url = put_object(object_name, data, content_type)

    # Fire async pipeline: thumbnails for images, 720p+poster for video.
    try:
        await publish(
            "media.uploaded",
            {
                "object_name": object_name,
                "media_type": media_type,
                "user_id": current.id,
            },
            key=str(current.id),
        )
    except Exception:
        pass  # original is already uploaded; variants are a nice-to-have

    return {"url": url, "media_type": media_type, "object_name": object_name}
