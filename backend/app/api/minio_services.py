# Root-admin-only management of registered MinIO connections that
# Projects can be assigned to (see models/minio_service.py,
# models/project.py). A brand-new service starts out "not_initialized"
# until an admin clicks Initialize, which creates its bucket
# (core/service_storage.py).

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core import service_storage
from app.core.crypto import encrypt_secret
from app.db.session import get_db
from app.models.client import Client
from app.models.minio_service import MinioService
from app.models.project import Project
from app.models.user import User
from app.schemas.minio_service import MinioServiceCreate, MinioServiceOut

router = APIRouter(prefix="/admin/minio-services", tags=["admin"])


def _get_minio_service_or_404(db: Session, minio_service_id: int) -> MinioService:
    service = db.get(MinioService, minio_service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MinIO service not found")
    return service


def _service_out(service: MinioService) -> MinioServiceOut:
    return MinioServiceOut(
        minio_service_id=service.minio_service_id,
        name=service.name,
        endpoint=service.endpoint,
        access_key=service.access_key,
        secure=service.secure,
        bucket=service.bucket,
        status=service_storage.check_status(service),
    )


@router.get("", response_model=list[MinioServiceOut])
def list_minio_services(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    services = db.query(MinioService).order_by(MinioService.name).all()
    return [_service_out(service) for service in services]


@router.post("", response_model=MinioServiceOut, status_code=status.HTTP_201_CREATED)
def create_minio_service(
    body: MinioServiceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(MinioService).filter(MinioService.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service with that name already exists")

    service = MinioService(
        name=body.name,
        endpoint=body.endpoint,
        access_key=body.access_key,
        encrypted_secret_key=encrypt_secret(body.secret_key),
        secure=body.secure,
        bucket=body.bucket,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return _service_out(service)


@router.post("/{minio_service_id}/initialize", response_model=MinioServiceOut)
def initialize_minio_service(
    minio_service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    service = _get_minio_service_or_404(db, minio_service_id)
    try:
        service_storage.initialize_bucket(service)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not initialize: {error}")
    return _service_out(service)


@router.delete("/{minio_service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_minio_service(
    minio_service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    service = _get_minio_service_or_404(db, minio_service_id)

    in_use_by_project = db.query(Project).filter(Project.minio_service_id == minio_service_id).first()
    if in_use_by_project is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one project is still assigned to this service",
        )
    # A client can be assigned a service before it has any project (its
    # projects would inherit the assignment), so that has to be checked
    # too -- not just the Project FK above.
    in_use_by_client = db.query(Client).filter(Client.minio_service_id == minio_service_id).first()
    if in_use_by_client is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A client is still assigned to this service",
        )

    service_storage.evict(service)
    db.delete(service)
    db.commit()
