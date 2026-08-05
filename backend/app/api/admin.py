# Root-admin-only user management. This is the "protected admin screen"
# that proves role-gating works end to end for Phase 1: a standard user
# hitting these routes gets a 403, a root_admin gets the data.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models.group import Group, UserGroupProject
from app.models.project import Project
from app.models.user import User
from app.schemas.group import GroupMembershipCreate
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    return db.query(User).order_by(User.user_id).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    already_exists = (
        db.query(User)
        .filter((User.username == body.username) | (User.email == body.email))
        .first()
    )
    if already_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already in use")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        global_role=body.global_role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/projects/{project_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_project_group_member(
    project_id: int,
    body: GroupMembershipCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    # Onboarding a user onto a project is exactly this: put them in one of
    # that project's three auto-created groups (see api/projects.py).
    # Permissions are never granted any other way (per the brief).
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    group_name = f"Project-{project.project_name}-{body.group_role}"
    group = db.query(Group).filter(Group.group_name == group_name).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    already_member = (
        db.query(UserGroupProject)
        .filter_by(user_id=user.user_id, group_id=group.group_id, project_id=project_id)
        .first()
    )
    if already_member is None:
        db.add(UserGroupProject(user_id=user.user_id, group_id=group.group_id, project_id=project_id))
        db.commit()
