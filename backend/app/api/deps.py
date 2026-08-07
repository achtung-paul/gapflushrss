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
from app.models.group import MANAGERS, Group, UserGroupProject
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


def user_can_manage_project(db: Session, user: User, project_id: int) -> bool:
    # A "Project Admin" (per the brief) isn't a role stored on the user --
    # it's just being a member of that specific project's Managers group.
    if user.global_role == GlobalRole.root_admin:
        return True

    project = db.get(Project, project_id)
    if project is None:
        return False

    managers_group_name = f"Project-{project.project_name}-{MANAGERS}"
    managers_group = db.query(Group).filter(Group.group_name == managers_group_name).first()
    if managers_group is None:
        return False

    membership = (
        db.query(UserGroupProject)
        .filter_by(user_id=user.user_id, project_id=project_id, group_id=managers_group.group_id)
        .first()
    )
    return membership is not None


def require_project_manager(db: Session, user: User, project_id: int) -> None:
    if not user_can_manage_project(db, user, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be root admin or a manager of this project",
        )


def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
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
