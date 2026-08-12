# Root-admin-only management of Postgres *servers* -- registered once,
# reused by api/admin_clients.py's create_client to auto-provision a
# brand-new, dedicated database for a client instead of requiring an
# admin to have pre-registered a PostgresService (api/postgres_services.py)
# by hand. See core/service_provisioning.py and models/postgres_server.py
# for why this is a separate concept from PostgresService.

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.service_db import CONNECT_TIMEOUT_SECONDS
from app.db.session import get_db
from app.models.postgres_server import PostgresServer
from app.models.postgres_service import PostgresService
from app.models.user import User
from app.schemas.postgres_server import PostgresServerCreate, PostgresServerOut

router = APIRouter(prefix="/admin/postgres-servers", tags=["admin"])


def _get_postgres_server_or_404(db: Session, postgres_server_id: int) -> PostgresServer:
    server = db.get(PostgresServer, postgres_server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postgres server not found")
    return server


def _check_status(server: PostgresServer) -> str:
    try:
        connection = psycopg2.connect(
            host=server.host,
            port=server.port,
            dbname="postgres",
            user=server.admin_username,
            password=decrypt_secret(server.encrypted_admin_password),
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
        connection.close()
    except Exception:
        return "unreachable"
    return "reachable"


def _server_out(server: PostgresServer) -> PostgresServerOut:
    return PostgresServerOut(
        postgres_server_id=server.postgres_server_id,
        name=server.name,
        host=server.host,
        port=server.port,
        admin_username=server.admin_username,
        status=_check_status(server),
    )


@router.get("", response_model=list[PostgresServerOut])
def list_postgres_servers(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    servers = db.query(PostgresServer).order_by(PostgresServer.name).all()
    return [_server_out(server) for server in servers]


@router.post("", response_model=PostgresServerOut, status_code=status.HTTP_201_CREATED)
def create_postgres_server(
    body: PostgresServerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(PostgresServer).filter(PostgresServer.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A server with that name already exists")

    server = PostgresServer(
        name=body.name,
        host=body.host,
        port=body.port,
        admin_username=body.admin_username,
        encrypted_admin_password=encrypt_secret(body.admin_password),
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return _server_out(server)


@router.delete("/{postgres_server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_postgres_server(
    postgres_server_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    server = _get_postgres_server_or_404(db, postgres_server_id)

    # Refused rather than orphaning provisioned_from_server_id on every
    # PostgresService this server ever created -- same "in use" reasoning
    # as api/postgres_services.py's delete_postgres_service, just checked
    # against the reverse relationship.
    in_use = db.query(PostgresService).filter(PostgresService.provisioned_from_server_id == postgres_server_id).first()
    if in_use is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one PostgresService was provisioned from this server",
        )

    db.delete(server)
    db.commit()
