# Project creation, listing, rename, and delete. Only a root_admin can
# do any of these -- there's no "manager of this project" to check for
# create (the project, and its groups, don't exist yet), and
# rename/delete are treated the same way since they're structural
# actions on the project itself, not on assets within it (which project
# managers already handle elsewhere). Reading the list is open to any
# logged-in user -- see the note in api/commodities.py about read
# visibility.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_root_admin
from app.core.storage import delete_image
from app.db.session import get_db
from app.models.commodity import Commodity
from app.models.group import CONTRIBUTORS, MANAGERS, VIEWERS, Group
from app.models.image import Image
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


# A project's three groups aren't linked to it by a foreign key (see
# models/group.py) -- they're found purely by reconstructing this name
# string, so renaming/deleting a project has to keep this in sync by
# hand.
def _group_name(project_name: str, role_name: str) -> str:
    return f"Project-{project_name}-{role_name}"


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
        db.add(Group(group_name=_group_name(body.project_name, role_name)))

    db.commit()
    db.refresh(project)
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    project = _get_project_or_404(db, project_id)

    existing = db.query(Project).filter(Project.project_name == body.project_name).first()
    if existing is not None and existing.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project name already exists")

    old_name = project.project_name
    project.project_name = body.project_name

    # Keep the three groups' names in sync with the new project name --
    # user_can_manage_project (api/deps.py) finds a group by
    # reconstructing this same name string, so leaving the old name in
    # place would silently break every member's permissions.
    for role_name in (MANAGERS, CONTRIBUTORS, VIEWERS):
        group = db.query(Group).filter(Group.group_name == _group_name(old_name, role_name)).first()
        if group is not None:
            group.group_name = _group_name(body.project_name, role_name)

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    project = _get_project_or_404(db, project_id)

    # MinIO objects have to be removed by hand before the delete below --
    # once the DB cascade removes the Image rows, their object_key (the
    # only record of where the file lives in MinIO) is gone for good.
    images = (
        db.query(Image)
        .join(Commodity, Image.commodity_id == Commodity.commodity_id)
        .filter(Commodity.project_id == project_id)
        .all()
    )
    for image in images:
        delete_image(image.object_key)

    # Groups aren't linked to the project by a foreign key, so nothing
    # cascades them -- delete by the same reconstructed name.
    for role_name in (MANAGERS, CONTRIBUTORS, VIEWERS):
        group = db.query(Group).filter(Group.group_name == _group_name(project.project_name, role_name)).first()
        if group is not None:
            db.delete(group)

    # Cascades to commodities -> analyses -> (entries -> chain
    # components; images -> markers) via ondelete="CASCADE".
    db.delete(project)
    db.commit()
