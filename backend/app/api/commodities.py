# Commodities live under a Project (brief: Project -> Commodity ->
# Analysis). Creating one requires being root_admin or a Manager of the
# parent project. Reading only requires being logged in *and* a member
# of the project (any of its three groups) -- enforced by get_project_db
# below resolving through api/deps.py's get_project, which 404s a
# project this user isn't a member of before this handler even runs.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_project_db, require_project_manager
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.project import Project
from app.models.user import User
from app.schemas.commodity import CommodityCreate, CommodityOut

router = APIRouter(prefix="/projects/{project_id}/commodities", tags=["commodities"])


@router.get("", response_model=list[CommodityOut])
def list_commodities(
    project_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    return (
        project_db.query(Commodity)
        .filter(Commodity.project_id == project_id)
        .order_by(Commodity.name)
        .all()
    )


@router.post("", response_model=CommodityOut, status_code=status.HTTP_201_CREATED)
def create_commodity(
    project_id: int,
    body: CommodityCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    # Manager-only, not require_project_editor -- the brief reserves
    # defining Commodities specifically for "Site Admins or Project
    # Admins" (a Project Admin being a Manager, see api/deps.py), unlike
    # the Contributor-writable Analysis/entry/marker/image routes
    # elsewhere in this app.
    require_project_manager(db, current_user, project_id)

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Unique per project, not system-wide (see models/commodity.py) --
    # two projects can share the same physical Postgres service, so this
    # has to filter by project_id explicitly, not just check the code
    # against the whole table.
    code_taken = (
        project_db.query(Commodity)
        .filter(Commodity.project_id == project_id, Commodity.code == body.code)
        .first()
    )
    if code_taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Commodity code already in use")

    commodity = Commodity(project_id=project_id, name=body.name, code=body.code)
    project_db.add(commodity)
    project_db.commit()
    project_db.refresh(commodity)
    return commodity
