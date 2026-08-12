# A client admin's management of their own client's users and project
# memberships. Every route here is scoped to current_user.client_id --
# nothing in this file can reach another client's data, and root_admin
# can't reach this file at all (require_client_admin rejects them, since
# their client_id is NULL -- see api/deps.py).

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_project, require_client_admin
from app.core.security import force_password_reset, hash_password
from app.db.session import get_db
from app.models.group import Group, UserGroupProject
from app.models.password_reset_token import PasswordResetToken
from app.models.project import Project
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession
from app.schemas.group import GroupMemberOut, GroupMembershipCreate, GroupRole
from app.schemas.user import ClientUserCreate, ClientUserUpdate, UserListOut, UserOut

router = APIRouter(prefix="/client-admin", tags=["client-admin"])

USERS_PAGE_SIZE = 25


def _get_client_user_or_404(db: Session, current_user: User, user_id: int) -> User:
    """Fetch a user, but only one belonging to the caller's own client.

    404 rather than 403 on a mismatch: a client admin must not be able to
    tell "that id belongs to another client" apart from "that id doesn't
    exist" -- same reasoning as api/deps.py's get_project, and the whole
    point of the sandbox. Every route below goes through this or its
    project twin (Depends(get_project)); none uses a bare db.get().
    """
    user = db.get(User, user_id)
    if user is None or user.client_id != current_user.client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _refuse_if_last_client_admin(db: Session, user: User) -> None:
    """Mirror of api/admin.py's _refuse_if_last_root_admin, scoped to a client.

    Demoting or deleting a client's only client_admin would leave that
    sandbox with nobody able to manage it, and root admin can't fix it
    directly (they can only register a *replacement* admin via
    /admin/clients/{id}/admins -- see api/admin_clients.py) -- so it's
    worth refusing outright rather than relying on that recovery path.
    """
    if user.global_role != GlobalRole.client_admin:
        return

    other_client_admins = (
        db.query(User)
        .filter(
            User.client_id == user.client_id,
            User.global_role == GlobalRole.client_admin,
            User.user_id != user.user_id,
        )
        .count()
    )
    if other_client_admins == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one client admin must remain",
        )


@router.get("/users", response_model=UserListOut)
def list_client_users(
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    query = db.query(User).filter(User.client_id == current_user.client_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (User.first_name.ilike(pattern))
            | (User.last_name.ilike(pattern))
            | (User.email.ilike(pattern))
        )

    total = query.count()
    items = (
        query.order_by(User.user_id)
        .offset((page - 1) * USERS_PAGE_SIZE)
        .limit(USERS_PAGE_SIZE)
        .all()
    )
    return UserListOut(items=items, total=total)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_client_user(
    body: ClientUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    already_exists = db.query(User).filter(User.email == body.email).first()
    if already_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    # client_id is forced to the caller's own -- never taken from the
    # request body -- and global_role is restricted by
    # ClientUserRole (schemas/user.py) to "standard"/"client_admin", so
    # a client admin can't mint a root admin even by sending the field.
    user = User(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password_hash=hash_password(body.password),
        global_role=GlobalRole(body.global_role),
        client_id=current_user.client_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_client_user(
    user_id: int,
    body: ClientUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    user = _get_client_user_or_404(db, current_user, user_id)

    email_taken = db.query(User).filter(User.email == body.email, User.user_id != user_id).first()
    if email_taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    # Same two guards as api/admin.py's update_user, scoped to this
    # client: don't let a client admin lock everyone (including
    # themselves) out of managing this sandbox.
    if body.global_role != "client_admin":
        if user_id == current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own client admin role",
            )
        _refuse_if_last_client_admin(db, user)

    user.first_name = body.first_name
    user.last_name = body.last_name
    user.email = body.email
    user.global_role = GlobalRole(body.global_role)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    if user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    user = _get_client_user_or_404(db, current_user, user_id)
    _refuse_if_last_client_admin(db, user)

    # None of these three FKs cascade on delete (see the model files), so
    # a plain db.delete(user) would fail with a foreign key violation the
    # moment the user has a session, a pending reset token, or any group
    # membership. Same "delete it by hand first" pattern as the
    # MinIO/Group gotchas noted in CLAUDE.md.
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    db.query(UserGroupProject).filter(UserGroupProject.user_id == user_id).delete()
    db.delete(user)
    db.commit()


@router.post("/users/{user_id}/force-password-reset", status_code=status.HTTP_204_NO_CONTENT)
def force_client_user_password_reset(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    user = _get_client_user_or_404(db, current_user, user_id)
    force_password_reset(db, user)
    db.commit()


@router.get("/projects/{project_id}/members", response_model=list[GroupMemberOut])
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),  # 404s on a project outside the caller's client
    _: User = Depends(require_client_admin),
):
    rows = (
        db.query(User, Group)
        .join(UserGroupProject, UserGroupProject.user_id == User.user_id)
        .join(Group, UserGroupProject.group_id == Group.group_id)
        .filter(UserGroupProject.project_id == project.project_id)
        .order_by(User.last_name, User.first_name)
        .all()
    )
    return [
        GroupMemberOut(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            group_role=group.role_name,
        )
        for user, group in rows
    ]


@router.post("/projects/{project_id}/members", status_code=status.HTTP_204_NO_CONTENT)
def add_project_group_member(
    project_id: int,
    body: GroupMembershipCreate,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    current_user: User = Depends(require_client_admin),
):
    # Onboarding a user onto a project is exactly this: put them in one of
    # that project's three auto-created groups (see api/projects.py).
    # Permissions are never granted any other way (per the brief).
    # _get_client_user_or_404 is what stops a client admin adding
    # *another client's* user to their own project -- a 404, not a
    # silent cross-tenant grant.
    user = _get_client_user_or_404(db, current_user, body.user_id)

    group = db.query(Group).filter_by(project_id=project.project_id, role_name=body.group_role).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    already_member = (
        db.query(UserGroupProject)
        .filter_by(user_id=user.user_id, group_id=group.group_id, project_id=project.project_id)
        .first()
    )
    if already_member is None:
        db.add(UserGroupProject(user_id=user.user_id, group_id=group.group_id, project_id=project.project_id))
        db.commit()


@router.delete("/projects/{project_id}/members/{group_role}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_group_member(
    project_id: int,
    group_role: GroupRole,
    user_id: int,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    _: User = Depends(require_client_admin),
):
    # Offboarding is the mirror of add_project_group_member above: drop
    # the one UserGroupProject row linking this user to this project's
    # group, nothing else.
    group = db.query(Group).filter_by(project_id=project.project_id, role_name=group_role).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    db.query(UserGroupProject).filter_by(
        user_id=user_id, group_id=group.group_id, project_id=project.project_id
    ).delete()
    db.commit()
