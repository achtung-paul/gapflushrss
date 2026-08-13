# A client admin's management of their own client's users and project
# memberships. Every route here is scoped to current_user.client_id --
# nothing in this file can reach another client's data, and root_admin
# can't reach this file at all (require_client_admin rejects them, since
# their client_id is NULL -- see api/deps.py).

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_project, require_client_admin
from app.core.invites import build_invited_user, send_account_invite
from app.core.security import force_password_reset
from app.core.security_events import (
    EVENT_PROJECT_MEMBER_ADDED,
    EVENT_PROJECT_MEMBER_REMOVED,
    EVENT_USER_2FA_RESET,
    EVENT_USER_CREATED,
    EVENT_USER_DELETED,
    EVENT_USER_INVITE_RESENT,
    EVENT_USER_PASSWORD_RESET_FORCED,
    EVENT_USER_ROLE_CHANGED,
    record_event,
)
from app.db.session import get_db
from app.models.group import Group, UserGroupProject
from app.models.login_challenge import LoginChallenge
from app.models.password_reset_token import PasswordResetToken
from app.models.project import Project
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession
from app.models.user_totp import UserTotp
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
    request: Request,
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
    # No password is set here -- the account starts unusable until the
    # invite link below is used (see core/invites.py).
    user = build_invited_user(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        global_role=GlobalRole(body.global_role),
        client_id=current_user.client_id,
    )
    db.add(user)
    db.flush()  # assigns user.user_id for the event below, without ending the transaction
    record_event(
        db,
        event_type=EVENT_USER_CREATED,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="user",
        target_id=user.user_id,
        target_name=user.email,
        detail=body.global_role,
    )
    db.commit()
    db.refresh(user)

    try:
        send_account_invite(db, user)
    except OSError as error:
        # The account was already created and committed above -- a mail
        # failure here doesn't roll that back, since the admin can retry
        # via resend-invite. Surfacing this as an error (rather than
        # swallowing it like request_password_reset does) matters
        # because the caller is an authenticated admin who needs to know
        # the new user has no way in yet.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User created, but the invite email failed to send: {error}",
        )
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_client_user(
    request: Request,
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

    # Compared before assigning: a name/email edit through this same form
    # is not a permission change and shouldn't be logged as one -- only
    # an actual change of global_role is a "user.role_changed" event.
    old_role = user.global_role.value
    user.first_name = body.first_name
    user.last_name = body.last_name
    user.email = body.email
    user.global_role = GlobalRole(body.global_role)
    if body.global_role != old_role:
        record_event(
            db,
            event_type=EVENT_USER_ROLE_CHANGED,
            actor=current_user,
            request=request,
            client_id=current_user.client_id,
            target_type="user",
            target_id=user.user_id,
            target_name=user.email,
            detail=f"{old_role} -> {body.global_role}",
        )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    if user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    user = _get_client_user_or_404(db, current_user, user_id)
    _refuse_if_last_client_admin(db, user)

    # None of these five FKs cascade on delete (see the model files), so
    # a plain db.delete(user) would fail with a foreign key violation the
    # moment the user has a session, a pending reset/invite token, a 2FA
    # enrollment, an in-progress login challenge, or any group
    # membership. Same "delete it by hand first" pattern as the
    # MinIO/Group gotchas noted in CLAUDE.md.
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    db.query(UserGroupProject).filter(UserGroupProject.user_id == user_id).delete()
    db.query(UserTotp).filter(UserTotp.user_id == user_id).delete()
    db.query(LoginChallenge).filter(LoginChallenge.user_id == user_id).delete()
    deleted_email = user.email  # captured before delete expires the object
    db.delete(user)
    record_event(
        db,
        event_type=EVENT_USER_DELETED,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="user",
        target_id=user_id,
        target_name=deleted_email,
    )
    db.commit()


@router.post("/users/{user_id}/force-password-reset", status_code=status.HTTP_204_NO_CONTENT)
def force_client_user_password_reset(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    user = _get_client_user_or_404(db, current_user, user_id)
    force_password_reset(db, user)
    record_event(
        db,
        event_type=EVENT_USER_PASSWORD_RESET_FORCED,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="user",
        target_id=user.user_id,
        target_name=user.email,
    )
    db.commit()


@router.post("/users/{user_id}/resend-invite", status_code=status.HTTP_204_NO_CONTENT)
def resend_client_user_invite(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    """Re-send the set-password link -- e.g. the original invite expired
    (7 days, see models/password_reset_token.py) or the email never
    arrived. Always issues a brand-new token rather than checking
    whether the account has already set a password; using an old, still
    valid link an admin resent is harmless even for an active account
    (see core/invites.py's send_account_invite docstring).
    """
    user = _get_client_user_or_404(db, current_user, user_id)
    try:
        send_account_invite(db, user)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to send invite email: {error}"
        )
    record_event(
        db,
        event_type=EVENT_USER_INVITE_RESENT,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="user",
        target_id=user.user_id,
        target_name=user.email,
    )
    db.commit()


@router.post("/users/{user_id}/reset-2fa", status_code=status.HTTP_204_NO_CONTENT)
def reset_client_user_2fa(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_client_admin),
):
    """Recovery path for a user who's lost their authenticator device --
    deletes their enrollment (and any in-progress login challenge) and
    kills their sessions, so the next login re-enrolls from scratch. This
    app has no self-service recovery codes; an admin resetting 2FA is the
    only way back in, the same shape as force-password-reset above.
    """
    user = _get_client_user_or_404(db, current_user, user_id)
    db.query(UserTotp).filter(UserTotp.user_id == user_id).delete()
    db.query(LoginChallenge).filter(LoginChallenge.user_id == user_id).delete()
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    record_event(
        db,
        event_type=EVENT_USER_2FA_RESET,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="user",
        target_id=user.user_id,
        target_name=user.email,
    )
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
    request: Request,
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
        record_event(
            db,
            event_type=EVENT_PROJECT_MEMBER_ADDED,
            actor=current_user,
            request=request,
            client_id=current_user.client_id,
            target_type="user",
            target_id=user.user_id,
            target_name=user.email,
            detail=f"{project.project_name} ({body.group_role})",
        )
        db.commit()


@router.delete("/projects/{project_id}/members/{group_role}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_group_member(
    request: Request,
    project_id: int,
    group_role: GroupRole,
    user_id: int,
    db: Session = Depends(get_db),
    project: Project = Depends(get_project),
    current_user: User = Depends(require_client_admin),
):
    # Offboarding is the mirror of add_project_group_member above: drop
    # the one UserGroupProject row linking this user to this project's
    # group, nothing else.
    group = db.query(Group).filter_by(project_id=project.project_id, role_name=group_role).first()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    removed = (
        db.query(UserGroupProject)
        .filter_by(user_id=user_id, group_id=group.group_id, project_id=project.project_id)
        .delete()
    )
    if removed:
        # Best-effort display name -- the user row itself is central data
        # this client admin can already see, so no extra tenancy check is
        # needed here (unlike the add path, which uses
        # _get_client_user_or_404 to check ownership before granting
        # anything).
        member = db.get(User, user_id)
        record_event(
            db,
            event_type=EVENT_PROJECT_MEMBER_REMOVED,
            actor=current_user,
            request=request,
            client_id=current_user.client_id,
            target_type="user",
            target_id=user_id,
            target_name=member.email if member is not None else None,
            detail=f"{project.project_name} ({group_role})",
        )
    db.commit()
