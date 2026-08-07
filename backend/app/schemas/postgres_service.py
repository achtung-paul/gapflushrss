from typing import Literal

from pydantic import BaseModel


class PostgresServiceCreate(BaseModel):
    name: str
    host: str
    port: int = 5432
    database: str
    username: str
    password: str


class PostgresServiceOut(BaseModel):
    # Built by hand in api/postgres_services.py, not model_validate'd
    # straight off a PostgresService row -- `status` isn't a column, it's
    # a live connectivity/initialization check (core/service_db.py's
    # check_status), and `password`/`encrypted_password` are deliberately
    # never included here at all.
    postgres_service_id: int
    name: str
    host: str
    port: int
    database: str
    username: str
    status: Literal["unreachable", "not_initialized", "initialized"]
