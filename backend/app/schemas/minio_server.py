from typing import Literal

from pydantic import BaseModel


class MinioServerCreate(BaseModel):
    name: str
    endpoint: str
    secure: bool = False
    root_access_key: str
    root_secret_key: str


class MinioServerOut(BaseModel):
    # Built by hand in api/minio_servers.py -- same reasoning as
    # MinioServiceOut (schemas/minio_service.py): `status` is a live
    # check, not a column, and the root secret key is never included here.
    minio_server_id: int
    name: str
    endpoint: str
    secure: bool
    root_access_key: str
    status: Literal["unreachable", "reachable"]
