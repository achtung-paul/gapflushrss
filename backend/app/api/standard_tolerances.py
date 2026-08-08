# A project's own named tolerance presets (see models/standard_tolerance.py).
# Reading is open to any project member (already enforced by
# get_project_db's dependency chain -- see api/deps.py's get_project);
# adding/editing/deleting is Manager-only ("project admins" -- unlike
# most Analysis-data writes elsewhere in this app, Contributors don't
# get this one, since it's project-wide configuration rather than data
# entry on one analysis).

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_project_db, require_project_manager
from app.db.session import get_db
from app.models.standard_tolerance import StandardTolerance
from app.models.user import User
from app.schemas.standard_tolerance import StandardToleranceCreate, StandardToleranceOut

router = APIRouter(prefix="/projects/{project_id}/standard-tolerances", tags=["standard-tolerances"])


def _get_standard_tolerance_or_404(
    project_db: Session, project_id: int, standard_tolerance_id: int
) -> StandardTolerance:
    standard = project_db.get(StandardTolerance, standard_tolerance_id)
    if standard is None or standard.project_id != project_id:
        # project_id is a plain column, not a real FK (see
        # models/standard_tolerance.py) -- same ownership-check reasoning
        # as Commodity.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standard tolerance not found")
    return standard


def _name_taken(project_db: Session, project_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = project_db.query(StandardTolerance).filter(
        StandardTolerance.project_id == project_id, StandardTolerance.name == name
    )
    if exclude_id is not None:
        query = query.filter(StandardTolerance.standard_tolerance_id != exclude_id)
    return query.first() is not None


@router.get("", response_model=list[StandardToleranceOut])
def list_standard_tolerances(
    project_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    return (
        project_db.query(StandardTolerance)
        .filter(StandardTolerance.project_id == project_id)
        .order_by(StandardTolerance.name)
        .all()
    )


@router.post("", response_model=StandardToleranceOut, status_code=status.HTTP_201_CREATED)
def create_standard_tolerance(
    project_id: int,
    body: StandardToleranceCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    require_project_manager(db, current_user, project_id)

    if _name_taken(project_db, project_id, body.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That name is already in use")

    standard = StandardTolerance(
        project_id=project_id,
        name=body.name,
        tolerance_value=body.tolerance_value,
        contributor_type=body.contributor_type,
        updated_by_name=f"{current_user.first_name} {current_user.last_name}",
        updated_at=datetime.now(timezone.utc),
    )
    project_db.add(standard)
    project_db.commit()
    project_db.refresh(standard)
    return standard


@router.put("/{standard_tolerance_id}", response_model=StandardToleranceOut)
def update_standard_tolerance(
    project_id: int,
    standard_tolerance_id: int,
    body: StandardToleranceCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    require_project_manager(db, current_user, project_id)
    standard = _get_standard_tolerance_or_404(project_db, project_id, standard_tolerance_id)

    if _name_taken(project_db, project_id, body.name, exclude_id=standard_tolerance_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That name is already in use")

    standard.name = body.name
    standard.tolerance_value = body.tolerance_value
    standard.contributor_type = body.contributor_type
    standard.updated_by_name = f"{current_user.first_name} {current_user.last_name}"
    standard.updated_at = datetime.now(timezone.utc)
    project_db.commit()
    project_db.refresh(standard)
    return standard


@router.delete("/{standard_tolerance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_standard_tolerance(
    project_id: int,
    standard_tolerance_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    require_project_manager(db, current_user, project_id)
    standard = _get_standard_tolerance_or_404(project_db, project_id, standard_tolerance_id)

    project_db.delete(standard)
    project_db.commit()
