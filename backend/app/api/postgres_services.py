# Root-admin-only management of registered Postgres connections that
# Projects can be assigned to (see models/postgres_service.py,
# models/project.py). A brand-new service starts out "not_initialized"
# until an admin clicks Initialize, which runs the project-scoped
# Alembic chain against it (core/service_db.py) -- see CLAUDE.md for why
# that chain is separate from this app's own migrations.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core import service_db
from app.core.crypto import encrypt_secret
from app.db.session import get_db
from app.models.postgres_service import PostgresService
from app.models.project import Project
from app.models.user import User
from app.schemas.postgres_service import PostgresServiceCreate, PostgresServiceOut

router = APIRouter(prefix="/admin/postgres-services", tags=["admin"])


def _get_postgres_service_or_404(db: Session, postgres_service_id: int) -> PostgresService:
    service = db.get(PostgresService, postgres_service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postgres service not found")
    return service


def _service_out(service: PostgresService) -> PostgresServiceOut:
    return PostgresServiceOut(
        postgres_service_id=service.postgres_service_id,
        name=service.name,
        host=service.host,
        port=service.port,
        database=service.database,
        username=service.username,
        status=service_db.check_status(service),
    )


@router.get("", response_model=list[PostgresServiceOut])
def list_postgres_services(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    services = db.query(PostgresService).order_by(PostgresService.name).all()
    return [_service_out(service) for service in services]


@router.post("", response_model=PostgresServiceOut, status_code=status.HTTP_201_CREATED)
def create_postgres_service(
    body: PostgresServiceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(PostgresService).filter(PostgresService.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A service with that name already exists")

    service = PostgresService(
        name=body.name,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        encrypted_password=encrypt_secret(body.password),
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return _service_out(service)


@router.post("/{postgres_service_id}/initialize", response_model=PostgresServiceOut)
def initialize_postgres_service(
    postgres_service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    service = _get_postgres_service_or_404(db, postgres_service_id)
    try:
        service_db.initialize_schema(service)
    except Exception as error:
        # Wrong credentials, unreachable host, DB doesn't exist, etc. --
        # not this app's bug, so 400 (bad service config) rather than 500.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Could not initialize: {error}")
    return _service_out(service)


@router.delete("/{postgres_service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_postgres_service(
    postgres_service_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    service = _get_postgres_service_or_404(db, postgres_service_id)

    in_use = db.query(Project).filter(Project.postgres_service_id == postgres_service_id).first()
    if in_use is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one project is still assigned to this service",
        )

    service_db.evict(service)
    db.delete(service)
    db.commit()
