# Root-admin-only management of *other root admins*. Renamed from
# /admin/users (which used to return every user in the system) to
# /admin/root-admins -- a route called /admin/users that only ever
# returns some users is a trap for the next reader. Client user
# management, and project group membership, live in api/client_admin.py
# now: root admin has no route that can reach them (see CLAUDE.md's
# tenancy-boundary gotcha).

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core.invites import build_invited_user, send_account_invite
from app.db.session import get_db
from app.models.login_challenge import LoginChallenge
from app.models.password_reset_token import PasswordResetToken
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession
from app.models.user_totp import UserTotp
from app.schemas.user import RootAdminCreate, RootAdminUpdate, UserListOut, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])

# Fixed page size for the user list -- the admin screen shows at most
# this many rows at once, with page/breadcrumb controls for the rest.
USERS_PAGE_SIZE = 25


def _refuse_if_last_root_admin(db: Session, user: User) -> None:
    """Block removing root_admin from the only account that still has it.

    There is no way back from this through the API: only a root_admin can
    edit users, so deleting the last one leaves nobody able to restore it,
    and recovery means editing the database by hand. Called by
    delete_user.
    """
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


@router.get("/root-admins", response_model=UserListOut)
def list_root_admins(
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    # Filtering to client_id IS NULL is what actually enforces "root
    # admin cannot see any client's users" for this route -- root_admin
    # accounts are the only ones with a NULL client_id (see models/user.py).
    query = db.query(User).filter(User.client_id.is_(None))
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


@router.post("/root-admins", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_root_admin(
    body: RootAdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    already_exists = db.query(User).filter(User.email == body.email).first()
    if already_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    # No role to pick -- every account created through this route is a
    # root_admin with no client, by definition. No password either --
    # see core/invites.py.
    user = build_invited_user(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        global_role=GlobalRole.root_admin,
        client_id=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        send_account_invite(db, user)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User created, but the invite email failed to send: {error}",
        )
    return user


@router.put("/root-admins/{user_id}", response_model=UserOut)
def update_root_admin(
    user_id: int,
    body: RootAdminUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    # Added alongside the username -> first/last name migration: existing
    # users got backfilled with a placeholder surname (see that
    # migration), and there was previously no way to fix a user's details
    # after creation at all. Password isn't editable here -- that stays
    # on the email-based reset-token flow (api/auth.py).
    user = db.query(User).filter(User.user_id == user_id, User.client_id.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    email_taken = (
        db.query(User).filter(User.email == body.email, User.user_id != user_id).first()
    )
    if email_taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    user.first_name = body.first_name
    user.last_name = body.last_name
    user.email = body.email
    db.commit()
    db.refresh(user)
    return user


@router.delete("/root-admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_root_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
):
    if user_id == current_user.user_id:
        # Otherwise a root admin could delete their own account and lock
        # everyone out of user management (no one left to undo it).
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    user = db.query(User).filter(User.user_id == user_id, User.client_id.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Self-deletion is already blocked above, but deleting the *other* last
    # root admin would leave the system with none at all.
    _refuse_if_last_root_admin(db, user)

    # None of these four FKs cascade on delete (see the model files), so
    # a plain db.delete(user) would fail with a foreign key violation the
    # moment the user has a session, a pending reset/invite token, a 2FA
    # enrollment, or an in-progress login challenge. Root admins have no
    # UserGroupProject rows to clean up (they're never group members --
    # see api/deps.py). Same "delete it by hand first" pattern as the
    # MinIO/Group gotchas noted in CLAUDE.md.
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    db.query(UserTotp).filter(UserTotp.user_id == user_id).delete()
    db.query(LoginChallenge).filter(LoginChallenge.user_id == user_id).delete()
    db.delete(user)
    db.commit()


@router.post("/root-admins/{user_id}/resend-invite", status_code=status.HTTP_204_NO_CONTENT)
def resend_root_admin_invite(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    user = db.query(User).filter(User.user_id == user_id, User.client_id.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        send_account_invite(db, user)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to send invite email: {error}"
        )


@router.post("/root-admins/{user_id}/reset-2fa", status_code=status.HTTP_204_NO_CONTENT)
def reset_root_admin_2fa(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    """Recovery path for a root admin who's lost their authenticator
    device -- mirrors api/client_admin.py's reset_client_user_2fa. A
    root admin can reset another root admin's 2FA (including their own,
    for testing) but this route has no self-reset restriction, same as
    every other root-admin route in this file.
    """
    user = db.query(User).filter(User.user_id == user_id, User.client_id.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.query(UserTotp).filter(UserTotp.user_id == user_id).delete()
    db.query(LoginChallenge).filter(LoginChallenge.user_id == user_id).delete()
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.commit()
