# FastAPI dependencies for authentication and authorization. Any route
# that needs to know who's calling it, or needs to restrict who's allowed
# to call it, takes one of these as an argument.

from datetime import datetime, timezone
from typing import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core import service_db
from app.core.config import settings
from app.db.session import get_db
from app.models.group import CONTRIBUTORS, MANAGERS, Group, UserGroupProject
from app.models.minio_service import MinioService
from app.models.postgres_service import PostgresService
from app.models.project import Project
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    session = db.get(UserSession, token)
    if session is None or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    return user


def require_root_admin(user: User = Depends(get_current_user)) -> User:
    if user.global_role != GlobalRole.root_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Root admin access required")
    return user


def require_client_admin(user: User = Depends(get_current_user)) -> User:
    # The client-side mirror of require_root_admin. root_admin is
    # deliberately NOT accepted here: per the brief, root admin
    # configures databases and storage and can never see inside a
    # client's sandbox -- not its users, not its projects, not its
    # reference data. Their client_id is NULL (see models/user.py), so
    # they fail this check for the same reason every other outsider does.
    if user.global_role != GlobalRole.client_admin or user.client_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client admin access required")
    return user


def _user_is_client_admin_for(user: User, project: Project) -> bool:
    # A client admin implicitly has Manager rights on every project in
    # their own client -- the same short-circuit root_admin used to have
    # system-wide, now bounded to exactly one client. They need no
    # UserGroupProject row for it.
    return (
        user.global_role == GlobalRole.client_admin
        and user.client_id is not None
        and user.client_id == project.client_id
    )


def _user_is_in_project_group(db: Session, user: User, project_id: int, role_name: str) -> bool:
    project = db.get(Project, project_id)
    if project is None:
        return False

    # The tenancy boundary, checked before anything else. A user can only
    # ever have rights inside their own client -- root_admin (client_id
    # NULL) never passes this, and neither would a stale UserGroupProject
    # row somehow left pointing at another client's project.
    if user.client_id is None or user.client_id != project.client_id:
        return False

    if _user_is_client_admin_for(user, project):
        return True

    group = db.query(Group).filter_by(project_id=project_id, role_name=role_name).first()
    if group is None:
        return False

    membership = (
        db.query(UserGroupProject)
        .filter_by(user_id=user.user_id, project_id=project_id, group_id=group.group_id)
        .first()
    )
    return membership is not None


def user_can_view_project(db: Session, user: User, project: Project) -> bool:
    # Unlike user_can_manage_project/user_can_edit_project, this doesn't
    # care *which* of the three groups the membership is in -- Managers,
    # Contributors, and Viewers can all see that the project exists.
    # Used by get_project below to 404 (not 403) a project a user isn't
    # a member of, so its existence isn't leaked to non-members either.
    #
    # Takes the Project itself, not a project_id -- its only caller
    # (get_project) already has it loaded, and the tenancy check below
    # needs the row anyway.
    if user.client_id is None or user.client_id != project.client_id:
        return False
    if _user_is_client_admin_for(user, project):
        return True
    return (
        db.query(UserGroupProject)
        .filter_by(user_id=user.user_id, project_id=project.project_id)
        .first()
        is not None
    )


def user_can_manage_project(db: Session, user: User, project_id: int) -> bool:
    # A "Project Admin" (per the brief) isn't a role stored on the user --
    # it's just being a member of that specific project's Managers group.
    # Managers can read/write/delete (per the brief's Managers/Contributors/
    # Viewers table) -- this is the delete-and-structural-changes check;
    # see user_can_edit_project for the create/update check.
    return _user_is_in_project_group(db, user, project_id, MANAGERS)


def user_can_edit_project(db: Session, user: User, project_id: int) -> bool:
    # Contributors can read/write but not delete (per the brief) -- so
    # anywhere a Manager can create/update, a Contributor can too. Only
    # delete routes (and Commodity creation, which the brief explicitly
    # reserves for "Site Admins or Project Admins") should use
    # user_can_manage_project/require_project_manager instead of this.
    return user_can_manage_project(db, user, project_id) or _user_is_in_project_group(
        db, user, project_id, CONTRIBUTORS
    )


def require_project_manager(db: Session, user: User, project_id: int) -> None:
    if not user_can_manage_project(db, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be a manager of this project (or its client admin)",
        )


def require_project_editor(db: Session, user: User, project_id: int) -> None:
    if not user_can_edit_project(db, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be a manager or contributor of this project (or its client admin)",
        )


def get_project(
    project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Project:
    project = db.get(Project, project_id)
    # A non-member (or a member of a *different* client entirely) gets
    # the same 404 as a project that doesn't exist at all -- every
    # project-scoped route resolves through here (directly or via
    # get_project_db/get_project_minio_service below), so this is the
    # one place that needs to hide a project's existence for it to be
    # hidden everywhere, including from root_admin.
    if project is None or not user_can_view_project(db, current_user, project):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def get_project_db(project: Project = Depends(get_project), db: Session = Depends(get_db)) -> Generator[Session, None, None]:
    # Commodity-and-below data doesn't live in this app's own central
    # database (the one `db` above connects to) -- it lives on whichever
    # Postgres service the Project was assigned at creation (see
    # core/service_db.py, models/project.py). Every project-scoped route
    # takes both `db` (central -- permission checks) and this
    # (the actual data), see api/commodities.py for the pattern.
    service = db.get(PostgresService, project.postgres_service_id)
    project_db = service_db.get_session(service)
    try:
        yield project_db
    finally:
        project_db.close()


def get_project_minio_service(project: Project = Depends(get_project), db: Session = Depends(get_db)) -> MinioService:
    # FastAPI caches `Depends(get_project)`'s result per request, so this
    # doesn't re-fetch the Project row that get_project_db already did --
    # both just take the same cached one, resolved once from project_id.
    return db.get(MinioService, project.minio_service_id)
