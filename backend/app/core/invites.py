# Shared helper for creating an account by email invite instead of an
# admin-chosen password -- used by every route that creates a user:
# api/admin.py's create_root_admin, api/client_admin.py's
# create_client_user, and api/admin_clients.py's create_client and
# add_client_admin.
#
# Lives here, not in api/auth.py, for the same reason core/security.py's
# PASSWORD_EXPIRY docstring gives for that constant: importing a helper
# out of one API router into three others would make those routers
# depend on each other, when the actually-shared thing is a plain
# function with no router attached to it. api/auth.py still owns the
# *consuming* side (confirm_password_reset) -- this module only issues
# the token and sends the email.

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import send_email
from app.core.security import generate_token, hash_unusable_password
from app.models.password_reset_token import (
    INVITE_TOKEN_LIFETIME,
    PURPOSE_INVITE,
    PasswordResetToken,
)
from app.models.user import GlobalRole, User

logger = logging.getLogger(__name__)


def build_invited_user(
    *, first_name: str, last_name: str, email: str, global_role: GlobalRole, client_id: int | None
) -> User:
    """A new User row that cannot log in with a password until the
    invite link below is used. Doesn't add/commit it -- some callers
    (e.g. admin_clients.py's create_client) need the row alongside other
    inserts in the same transaction, so committing here would take that
    choice away from them.
    """
    return User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_unusable_password(),
        global_role=global_role,
        client_id=client_id,
    )


def send_account_invite(db: Session, user: User) -> None:
    """Issue a fresh invite token for `user` and email the set-password
    link.

    Unlike api/auth.py's request_password_reset (which swallows a mail
    failure to avoid leaking whether an address exists), this lets
    send_email's OSError/SMTPException propagate -- the caller here is
    always an authenticated admin who just created this account on
    purpose, and needs to know the email didn't go out rather than being
    told everything's fine. Callers should catch it and surface a 502;
    the account itself stays created either way, so a resend-invite
    route (mirroring the existing force-password-reset routes) is the
    recovery path, not a rollback.

    Requires `user` to already have a user_id (added/flushed or
    committed by the caller) -- the token references it.
    """
    token = PasswordResetToken(
        token=generate_token(),
        user_id=user.user_id,
        purpose=PURPOSE_INVITE,
        expires_at=datetime.now(timezone.utc) + INVITE_TOKEN_LIFETIME,
    )
    db.add(token)
    db.commit()

    invite_link = f"{settings.frontend_origin}/set-password?token={token.token}"
    send_email(
        to_address=user.email,
        subject="Set up your GapFlush RSS account",
        body=(
            "An account has been created for you.\n\n"
            f"Set your password using this link (valid for {INVITE_TOKEN_LIFETIME.days} days):\n\n"
            f"{invite_link}"
        ),
    )
