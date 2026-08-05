# Commodities live under a Project (brief: Project -> Commodity ->
# Analysis). Creating one requires being root_admin or a Manager of the
# parent project; reading the list only requires being logged in.
#
# Note on scope: the brief's Viewers group implies project membership
# should also gate *reading* data, but Phase 2 doesn't build that
# finer-grained visibility check -- any logged-in user can currently list
# any project's commodities/analyses. Only writes are project-scoped.
# Worth tightening later if read-isolation between projects matters.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_manager
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.project import Project
from app.models.user import User
from app.schemas.commodity import CommodityCreate, CommodityOut

router = APIRouter(prefix="/projects/{project_id}/commodities", tags=["commodities"])


@router.get("", response_model=list[CommodityOut])
def list_commodities(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(Commodity)
        .filter(Commodity.project_id == project_id)
        .order_by(Commodity.name)
        .all()
    )


@router.post("", response_model=CommodityOut, status_code=status.HTTP_201_CREATED)
def create_commodity(
    project_id: int,
    body: CommodityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_manager(db, current_user, project_id)

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    code_taken = db.query(Commodity).filter(Commodity.code == body.code).first()
    if code_taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Commodity code already in use")

    commodity = Commodity(project_id=project_id, name=body.name, code=body.code)
    db.add(commodity)
    db.commit()
    db.refresh(commodity)
    return commodity
