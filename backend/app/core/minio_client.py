from io import BytesIO
from minio import Minio
from minio.error import S3Error

from app.core.config import settings

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket() -> None:
    client = get_minio()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def put_object(object_name: str, data: bytes, content_type: str) -> str:
    client = get_minio()
    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{settings.minio_public_endpoint}/{settings.minio_bucket}/{object_name}"


def remove_object(object_name: str) -> None:
    try:
        get_minio().remove_object(settings.minio_bucket, object_name)
    except S3Error:
        pass
