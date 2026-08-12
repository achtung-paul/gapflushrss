from typing import Literal

from pydantic import BaseModel


class PostgresServerCreate(BaseModel):
    name: str
    host: str
    port: int = 5432
    admin_username: str
    admin_password: str


class PostgresServerOut(BaseModel):
    # Built by hand in api/postgres_servers.py -- same reasoning as
    # PostgresServiceOut (schemas/postgres_service.py): `status` is a
    # live connectivity check, not a column, and the admin password is
    # never included here.
    postgres_server_id: int
    name: str
    host: str
    port: int
    admin_username: str
    status: Literal["unreachable", "reachable"]
