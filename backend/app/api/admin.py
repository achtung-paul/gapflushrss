# Root-admin-only user and project-group management. This is the
# "protected admin screen" that proves role-gating works end to end for
# Phase 1: a standard user hitting these routes gets a 403, a
# root_admin gets the data.

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.api.projects import _get_project_or_404, _group_name
from app.core.security import hash_password
from app.db.session import get_db
from app.models.group import CONTRIBUTORS, MANAGERS, VIEWERS, Group, UserGroupProject
from app.models.password_reset_token import PasswordResetToken
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession
from app.schemas.group import GroupMemberOut, GroupMembershipCreate, GroupRole
from app.schemas.user import UserCreate, UserListOut, UserOut, UserUpdate

router = APIRouter(prefix="/admin", tags=["admin"])

# Fixed page size for the user list -- the admin screen shows at most
# this many rows at once, with page/breadcrumb controls for the rest.
USERS_PAGE_SIZE = 25


def _refuse_if_last_root_admin(db: Session, user: User) -> None:
    """Block removing root_admin from the only account that still has it.

    There is no way back from this through the API: only a root_admin can
    edit users, so demoting or deleting the last one leaves nobody able to
    restore it, and recovery means editing the database by hand. Called by
    both update_user (on a role change) and delete_user.
    """
    if user.global_role != GlobalRole.root_admin:
        return

    other_root_admins = (
        db.query(User)
        .filter(User.global_role == GlobalRole.root_admin, User.user_id != user.user_id)
        .count()
    )
    if other_root_admins == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one root admin must remain",
        )


@router.get("/users", response_model=UserListOut)
def list_users(
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    query = db.query(User)
    if search:
        # Case-insensitive substring match on first name, last name, or
        # email -- matches the columns shown in the admin table.
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
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    already_exists = db.query(User).filter(User.email == body.email).first()
    if already_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    user = User(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password_hash=hash_password(body.password),
        global_role=body.global_role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
):
    # Added alongside the username -> first/last name migration: existing
    # users got backfilled with a placeholder surname (see that
    # migration), and there was previously no way to fix a user's details
    # after creation at all. Password isn't editable here -- that stays
    # on the email-based reset-token flow (api/auth.py).
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    email_taken = (
        db.query(User).filter(User.email == body.email, User.user_id != user_id).first()
    )
    if email_taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    # Guard the two ways this endpoint could lock everyone out of user
    # management. Only checked when the role is actually being lowered, so
    # editing your own name or email still works normally.
    if body.global_role != GlobalRole.root_admin:
        if user_id == current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own root admin role",
            )
        _refuse_if_last_root_admin(db, user)

    user.first_name = body.first_name
    user.last_name = body.last_name
    user.email = body.email
    user.global_role = body.global_role
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
):
    if user_id == current_user.user_id:
        # Otherwise a root admin could delete their own account and lock
        # everyone out of user management (no one left to undo it).
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Self-deletion is already blocked above, but deleting the *other* last
    # root admin would leave the system with none at all.
    _refuse_if_last_root_admin(db, user)

    # None of these three FKs cascade on delete (see the model files),
    # so a plain db.delete(user) would fail with a foreign key violation
    # the moment the user has a session, a pending reset token, or any
    # group membership. Same "delete it by hand first" pattern as the
    # MinIO/Group gotchas noted in CLAUDE.md.
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    db.query(UserGroupProject).filter(UserGroupProject.user_id == user_id).delete()
    db.delete(user)
    db.commit()


@router.get("/projects/{project_id}/members", response_model=list[GroupMemberOut])
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    project = _get_project_or_404(db, project_id)

    # Reverse of _group_name: which of this project's three groups
    # (found by name -- see api/projects.py, groups have no FK to
    # Project) corresponds to which role.
    role_by_group_name = {
        _group_name(project.project_name, role): role for role in (MANAGERS, CONTRIBUTORS, VIEWERS)
    }

    rows = (
        db.query(User, Group)
        .join(UserGroupProject, UserGroupProject.user_id == User.user_id)
        .join(Group, UserGroupProject.group_id == Group.group_id)
        .filter(UserGroupProject.project_id == project_id)
        .order_by(User.last_name, User.first_name)
        .all()
    )
    return [
        GroupMemberOut(
            user_id=user.user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            group_role=role_by_group_name[group.group_name],
        )
        for user, group in rows
        if group.group_name in role_by_group_name
    ]


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
    project = _get_project_or_404(db, project_id)

    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    group_name = _group_name(project.project_name, body.group_role)
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


@router.delete("/projects/{project_id}/members/{group_role}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_group_member(
    project_id: int,
    group_role: GroupRole,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    # Offboarding is the mirror of add_project_group_member above: drop
    # the one UserGroupProject row linking this user to this project's
    # group, nothing else.
    project = _get_project_or_404(db, project_id)

    group_name = _group_name(project.project_name, group_role)
    group = db.query(Group).filter(Group.group_name == group_name).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    db.query(UserGroupProject).filter_by(
        user_id=user_id, group_id=group.group_id, project_id=project_id
    ).delete()
    db.commit()
