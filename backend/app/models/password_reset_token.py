# A one-time token emailed to a user, either to let them reset a
# forgotten password or to let a newly-created account set its first one
# (an "invite"). See api/auth.py for how these are created and consumed.
#
# One table for both purposes rather than a second near-identical table:
# the only real differences are the email wording, the landing-page
# copy, and how long the link stays valid -- the token shape itself
# (single-use, expires, points at one user) is identical. `purpose` is a
# plain string, not a Postgres enum, deliberately -- adding an enum
# *column* to an existing table needs an explicit CREATE TYPE that
# autogenerate won't produce on its own (see CLAUDE.md's Alembic enum
# gotcha), which isn't worth it for a two-value flag used only in Python.

from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RESET_TOKEN_LIFETIME = timedelta(hours=1)

# Longer than a reset link: this is the first thing a brand-new user
# sees, and it has to survive a weekend, a holiday, or a slow corporate
# mail filter before the admin has to notice and re-send it (see
# resend-invite routes in api/client_admin.py etc.).
INVITE_TOKEN_LIFETIME = timedelta(days=7)

PURPOSE_RESET = "reset"
PURPOSE_INVITE = "invite"


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    # "reset" or "invite" (see PURPOSE_RESET/PURPOSE_INVITE above) --
    # only changes which email/landing-page copy is used and how the
    # expiry was set at creation; confirm_password_reset treats both
    # identically once the token itself is presented.
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default=PURPOSE_RESET)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + RESET_TOKEN_LIFETIME,
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
