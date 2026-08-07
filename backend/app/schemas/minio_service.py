from typing import Literal

from pydantic import BaseModel


class MinioServiceCreate(BaseModel):
    name: str
    endpoint: str
    access_key: str
    secret_key: str
    secure: bool = False
    bucket: str


class MinioServiceOut(BaseModel):
    # Built by hand in api/minio_services.py -- same reasoning as
    # PostgresServiceOut (see schemas/postgres_service.py): `status` is a
    # live check, not a column, and the secret key is never included here.
    minio_service_id: int
    name: str
    endpoint: str
    access_key: str
    secure: bool
    bucket: str
    status: Literal["unreachable", "not_initialized", "initialized"]
