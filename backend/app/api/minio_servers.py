# Root-admin-only management of MinIO *servers* -- registered once,
# reused by api/admin_clients.py's create_client to auto-provision a
# brand-new, bucket-scoped MinioService for a client instead of requiring
# an admin to have pre-registered one by hand
# (api/minio_services.py). See core/service_provisioning.py and
# models/minio_server.py for why this is a separate concept from
# MinioService.

from fastapi import APIRouter, Depends, HTTPException, status
from minio import Minio
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core.crypto import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models.minio_server import MinioServer
from app.models.minio_service import MinioService
from app.models.user import User
from app.schemas.minio_server import MinioServerCreate, MinioServerOut

router = APIRouter(prefix="/admin/minio-servers", tags=["admin"])


def _get_minio_server_or_404(db: Session, minio_server_id: int) -> MinioServer:
    server = db.get(MinioServer, minio_server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MinIO server not found")
    return server


def _check_status(server: MinioServer) -> str:
    try:
        client = Minio(
            server.endpoint,
            access_key=server.root_access_key,
            secret_key=decrypt_secret(server.encrypted_root_secret_key),
            secure=server.secure,
        )
        # A root-level, cheap call -- just proves the endpoint is
        # reachable and these credentials are actually valid, the same
        # thing MinioService's own check_status proves for one bucket
        # (core/service_storage.py).
        client.list_buckets()
    except Exception:
        return "unreachable"
    return "reachable"


def _server_out(server: MinioServer) -> MinioServerOut:
    return MinioServerOut(
        minio_server_id=server.minio_server_id,
        name=server.name,
        endpoint=server.endpoint,
        secure=server.secure,
        root_access_key=server.root_access_key,
        status=_check_status(server),
    )


@router.get("", response_model=list[MinioServerOut])
def list_minio_servers(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    servers = db.query(MinioServer).order_by(MinioServer.name).all()
    return [_server_out(server) for server in servers]


@router.post("", response_model=MinioServerOut, status_code=status.HTTP_201_CREATED)
def create_minio_server(
    body: MinioServerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(MinioServer).filter(MinioServer.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A server with that name already exists")

    server = MinioServer(
        name=body.name,
        endpoint=body.endpoint,
        secure=body.secure,
        root_access_key=body.root_access_key,
        encrypted_root_secret_key=encrypt_secret(body.root_secret_key),
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return _server_out(server)


@router.delete("/{minio_server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_minio_server(
    minio_server_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    server = _get_minio_server_or_404(db, minio_server_id)

    in_use = db.query(MinioService).filter(MinioService.provisioned_from_server_id == minio_server_id).first()
    if in_use is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one MinioService was provisioned from this server",
        )

    db.delete(server)
    db.commit()
