# MinIO (S3-compatible) object storage, resolved per MinioService
# (models/minio_service.py) instead of one hardcoded bucket -- replaces
# the old core/storage.py, which assumed a single global client.
#
# We keep upload/download simple, same as before: the whole uploaded
# file is read into memory first (fine for the photo-sized images this
# app deals with), then written to MinIO in one call. Reading it back
# streams straight from MinIO through the backend to the browser (see
# api/images.py) rather than using presigned URLs, so the browser never
# needs to talk to MinIO directly.

import logging
from io import BytesIO
from typing import Literal

from minio import Minio

from app.core.crypto import decrypt_secret
from app.models.minio_service import MinioService

logger = logging.getLogger(__name__)

ServiceStatus = Literal["unreachable", "not_initialized", "initialized"]

# Client cache per service -- same reasoning as core/service_db.py's
# engine cache: fine for one worker process, would need a lock for
# multiple.
_client_cache: dict[int, Minio] = {}


def get_client(service: MinioService) -> Minio:
    if service.minio_service_id not in _client_cache:
        _client_cache[service.minio_service_id] = Minio(
            service.endpoint,
            access_key=service.access_key,
            secret_key=decrypt_secret(service.encrypted_secret_key),
            secure=service.secure,
        )
    return _client_cache[service.minio_service_id]


def evict(service: MinioService) -> None:
    _client_cache.pop(service.minio_service_id, None)


def check_status(service: MinioService) -> ServiceStatus:
    try:
        exists = get_client(service).bucket_exists(service.bucket)
    except Exception:
        # Same reasoning as service_db.check_status -- any failure
        # (bad credentials, unreachable endpoint, ...) reads the same
        # way to an admin: this connection doesn't work right now. Logged
        # rather than discarded so the reason is available in the admin
        # log viewer when a service shows as unreachable.
        logger.warning("MinIO service %r is unreachable", service.name, exc_info=True)
        return "unreachable"
    return "initialized" if exists else "not_initialized"


def initialize_bucket(service: MinioService) -> None:
    if not get_client(service).bucket_exists(service.bucket):
        get_client(service).make_bucket(service.bucket)


def upload_image(service: MinioService, object_key: str, data: bytes, content_type: str) -> None:
    get_client(service).put_object(
        service.bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def get_image_stream(service: MinioService, object_key: str):
    # Caller is responsible for closing/releasing this (see api/images.py)
    # -- it holds an open HTTP connection to MinIO until then.
    return get_client(service).get_object(service.bucket, object_key)


def delete_image(service: MinioService, object_key: str) -> None:
    get_client(service).remove_object(service.bucket, object_key)
