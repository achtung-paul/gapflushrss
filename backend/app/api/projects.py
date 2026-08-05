# Project creation and listing. Only a root_admin can create a project
# (there's no "manager of this project" to check yet until the project,
# and its groups, exist). Reading the list is open to any logged-in user
# -- see the note in api/commodities.py about read visibility.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_root_admin
from app.db.session import get_db
from app.models.group import CONTRIBUTORS, MANAGERS, VIEWERS, Group
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Project).order_by(Project.project_name).all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(Project).filter(Project.project_name == body.project_name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project name already exists")

    project = Project(project_name=body.project_name)
    db.add(project)
    db.flush()  # assigns project.project_id without ending the transaction

    for role_name in (MANAGERS, CONTRIBUTORS, VIEWERS):
        db.add(Group(group_name=f"Project-{body.project_name}-{role_name}"))

    db.commit()
    db.refresh(project)
    return project
