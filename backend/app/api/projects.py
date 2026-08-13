# Project creation, listing, rename, and delete -- scoped to the caller's
# own Client throughout. Only a client_admin can create/rename/delete --
# there's no "manager of this project" to check for create (the project,
# and its groups, don't exist yet), and rename/delete are treated the
# same way since they're structural actions on the project itself, not
# on assets within it (which project managers already handle elsewhere).
# Reading the list is open to any logged-in user, but only shows projects
# within their own client that they're actually a member of (a client
# admin sees every project in their client) -- see api/deps.py's
# get_project for the matching 404-not-403 treatment of a project a user
# can't see, which is what actually hides its existence from direct
# navigation too, including from root_admin.

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.analyses import delete_analysis_images_from_storage
from app.api.deps import (
    _user_is_client_admin_for,
    get_current_user,
    get_project,
    get_project_db,
    get_project_minio_service,
    require_client_admin,
)
from app.core import service_storage
from app.core.security_events import EVENT_PROJECT_CREATED, EVENT_PROJECT_DELETED, record_event
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.client import Client
from app.models.commodity import Commodity
from app.models.group import CONTRIBUTORS, MANAGERS, VIEWERS, Group, UserGroupProject
from app.models.image import Image
from app.models.minio_service import MinioService
from app.models.project import Project
from app.models.user import GlobalRole, User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


# Everyone's role is whichever of the three groups they belong to --
# highest-privilege one wins if they're somehow in more than one. A
# client admin isn't a member of any group (see
# _user_is_client_admin_for) but implicitly outranks all three, so it's
# checked first and reported as its own label.
def _resolve_my_role(db: Session, user: User, project: Project) -> str:
    if _user_is_client_admin_for(user, project):
        return "Client Admin"
    for role_name, display_name in ((MANAGERS, "Manager"), (CONTRIBUTORS, "Contributor"), (VIEWERS, "Viewer")):
        group = db.query(Group).filter_by(project_id=project.project_id, role_name=role_name).first()
        if group is None:
            continue
        membership = (
            db.query(UserGroupProject)
            .filter_by(user_id=user.user_id, project_id=project.project_id, group_id=group.group_id)
            .first()
        )
        if membership is not None:
            return display_name
    return "Viewer"  # shouldn't happen -- list_projects only returns projects the user is a member of


def _project_out(db: Session, project: Project, current_user: User) -> ProjectOut:
    return ProjectOut(
        project_id=project.project_id,
        project_name=project.project_name,
        postgres_service_id=project.postgres_service_id,
        minio_service_id=project.minio_service_id,
        my_role=_resolve_my_role(db, current_user, project),
    )


def _is_client_admin(user: User) -> bool:
    return user.global_role == GlobalRole.client_admin and user.client_id is not None


def purge_project_data(project_db: Session, minio_service: MinioService, project_id: int) -> None:
    """Delete every Commodity (and everything under it) for one project.

    Shared by delete_project below and api/admin_clients.py's
    delete_client, which purges every project of a client one at a time
    -- kept as one function so there's only one place that has to get
    the MinIO-before-rows ordering right (CLAUDE.md's MinIO gotcha).
    Does not touch the Project row itself or its Groups -- callers do
    that afterward, on the central `db` session, since those tables
    aren't reachable from here.
    """
    # MinIO objects have to be removed by hand before the rows below --
    # once they're gone, object_key (the only record of where a file
    # lives) is gone for good. Covers both galleries: the Commodity's
    # single annotated image (Image) and each Analysis's plain photo
    # gallery (AnalysisImage) -- the latter wasn't cleaned up here
    # before this project's data moved to a separate database; fixed
    # here since MinIO cleanup now has to happen explicitly regardless.
    commodities = project_db.query(Commodity).filter(Commodity.project_id == project_id).all()
    commodity_ids = [commodity.commodity_id for commodity in commodities]

    images = project_db.query(Image).filter(Image.commodity_id.in_(commodity_ids)).all()
    for image in images:
        service_storage.delete_image(minio_service, image.object_key)

    analysis_ids = [
        row.analysis_id
        for row in project_db.query(Analysis.analysis_id)
        .filter(Analysis.commodity_id.in_(commodity_ids))
        .all()
    ]
    # Shared with api/images.py's delete_marker -- see that helper for why
    # this has to happen before the rows are deleted.
    delete_analysis_images_from_storage(project_db, minio_service, analysis_ids)

    # Deletes every Commodity for this project, cascading *within this
    # database* to everything under it (Analysis -> AnalysisEntry ->
    # ChainComponent; Image -> Marker; Analysis -> AnalysisImage) --
    # those FKs are still intra-database, only the Project<->Commodity
    # link crosses databases now (see models/commodity.py). Never drops
    # any tables: other projects may be colocated on this same service.
    for commodity in commodities:
        project_db.delete(commodity)
    project_db.commit()


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Always scoped to the caller's own client first -- root_admin's
    # client_id is NULL, which matches no project's client_id, so they
    # get an empty list rather than a 403 (their Projects link is simply
    # empty, not an error).
    query = db.query(Project).filter(Project.client_id == current_user.client_id)
    if not _is_client_admin(current_user):
        # Membership in any of a project's three groups is enough to see
        # it in the list -- same "any group counts" rule as
        # api/deps.py's user_can_view_project. A client admin skips this
        # join entirely and sees every project in their client.
        query = query.join(UserGroupProject, UserGroupProject.project_id == Project.project_id).filter(
            UserGroupProject.user_id == current_user.user_id
        )
    projects = query.order_by(Project.project_name).distinct().all()
    return [_project_out(db, project, current_user) for project in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    request: Request,
    body: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    existing = (
        db.query(Project)
        .filter(Project.client_id == current_user.client_id, Project.project_name == body.project_name)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project name already exists")

    # A client admin can't choose a service -- a new project always
    # inherits its client's dedicated Postgres/MinIO (see
    # models/client.py). Both are guaranteed already initialized: a
    # Client can't be created pointing at a service that isn't (see
    # api/admin_clients.py's create_client), so there's nothing left to
    # re-check here the way the old root-admin create_project had to.
    client = db.get(Client, current_user.client_id)

    project = Project(
        client_id=client.client_id,
        project_name=body.project_name,
        postgres_service_id=client.postgres_service_id,
        minio_service_id=client.minio_service_id,
    )
    db.add(project)
    db.flush()  # assigns project.project_id without ending the transaction

    for role_name in (MANAGERS, CONTRIBUTORS, VIEWERS):
        db.add(Group(project_id=project.project_id, role_name=role_name))

    record_event(
        db,
        event_type=EVENT_PROJECT_CREATED,
        actor=current_user,
        request=request,
        client_id=client.client_id,
        target_type="project",
        target_id=project.project_id,
        target_name=project.project_name,
    )
    db.commit()
    db.refresh(project)
    return _project_out(db, project, current_user)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    current_user: User = Depends(require_client_admin),
):
    existing = (
        db.query(Project)
        .filter(Project.client_id == project.client_id, Project.project_name == body.project_name)
        .first()
    )
    if existing is not None and existing.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project name already exists")

    # Renaming no longer touches groups at all -- they're linked to this
    # project by project_id, not by a name string built from
    # project_name, so nothing here can go out of sync.
    project.project_name = body.project_name

    db.commit()
    db.refresh(project)
    return _project_out(db, project, current_user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(require_client_admin),
):
    purge_project_data(project_db, minio_service, project_id)

    # Groups now carry a real FK to Project (ondelete="CASCADE"), so
    # deleting the project below takes its three groups -- and every
    # UserGroupProject row pointing at them -- with it automatically.
    project_name = project.project_name  # captured before delete expires the object
    db.delete(project)
    record_event(
        db,
        event_type=EVENT_PROJECT_DELETED,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="project",
        target_id=project_id,
        target_name=project_name,
    )
    db.commit()
