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

from fastapi import BackgroundTasks
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


def _send_invite_email(to_address: str, invite_link: str) -> None:
    # Run via BackgroundTasks, after the response has already gone out --
    # see send_account_invite's comment below on why. Its own try/except
    # since a route's exception handling can no longer catch anything
    # raised after the response is sent (same shape as api/auth.py's
    # _send_password_reset_email).
    try:
        send_email(
            to_address=to_address,
            subject="Set up your GapFlush RSS account",
            body=(
                "An account has been created for you.\n\n"
                f"Set your password using this link (valid for {INVITE_TOKEN_LIFETIME.days} days):\n\n"
                f"{invite_link}"
            ),
        )
    except OSError:
        logger.exception("Failed to send account invite email")


def send_account_invite(db: Session, user: User, background_tasks: BackgroundTasks) -> None:
    """Issue a fresh invite token for `user` and email the set-password
    link.

    send_email is a blocking network call (core/email.py) -- up to
    EMAIL_TIMEOUT_SECONDS -- so, like api/auth.py's
    request_password_reset, the actual send is deferred to run after the
    response via BackgroundTasks rather than inline in the request. That
    means a caller here can no longer be told synchronously that the
    email failed to send (there used to be a try/except OSError -> 502
    around this call; that's gone now, on purpose) -- a stalled mail
    server no longer holds an admin's request open for up to
    EMAIL_TIMEOUT_SECONDS, and the account row (already committed by the
    time this is called) is never left half-done by an email failure.
    The existing "Resend invite" routes are the recovery path either
    way, same as before this change -- they were already the answer for
    "the email never arrived", just now also the answer for "the send
    failed outright".

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
    background_tasks.add_task(_send_invite_email, user.email, invite_link)
