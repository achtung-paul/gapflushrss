# MinIO (S3-compatible) object storage for analysis images.
#
# We keep this simple: the whole uploaded file is read into memory first
# (fine for the photo-sized images this app deals with), then written to
# MinIO in one call. Reading it back streams straight from MinIO through
# the backend to the browser -- see api/images.py -- rather than using
# presigned URLs, so the browser never needs to talk to MinIO directly.

from io import BytesIO

from minio import Minio

from app.core.config import settings

client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket_exists() -> None:
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_image(object_key: str, data: bytes, content_type: str) -> None:
    client.put_object(
        settings.minio_bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def get_image_stream(object_key: str):
    # Caller is responsible for closing/releasing this (see api/images.py)
    # -- it holds an open HTTP connection to MinIO until then.
    return client.get_object(settings.minio_bucket, object_key)


def delete_image(object_key: str) -> None:
    client.remove_object(settings.minio_bucket, object_key)
