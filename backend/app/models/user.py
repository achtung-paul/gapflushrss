# The Users table. Login is by email + password (see api/auth.py) --
# there's no separate username. first_name/last_name are what's shown
# everywhere a person needs to be identified (header, admin user list,
# project member list, "last modified by" columns) instead.
#
# global_role has three values now: "root_admin" (an infrastructure
# operator -- configures Postgres/MinIO services and registers clients,
# and per the brief can never see inside a client's sandbox), "client_admin"
# (implicitly has Manager rights on every project in their own client --
# see api/deps.py's _user_is_client_admin_for), and "standard" (an
# ordinary user, whose project access comes entirely from which Group
# they belong to in that project -- see UserGroupProject in group.py).
#
# client_id is the tenancy boundary itself: which Client's sandbox this
# user belongs to. It's nullable, and that NULL is deliberate -- a
# root_admin has no client, and every permission check in api/deps.py
# that compares client_id treats NULL as "matches nothing", which is
# exactly how root_admin ends up with no access to any client's data.
# Don't "fix" a root_admin's NULL client_id by giving them one; the NULL
# is the mechanism, not a gap.

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GlobalRole(str, enum.Enum):
    root_admin = "root_admin"
    client_admin = "client_admin"
    standard = "standard"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    global_role: Mapped[GlobalRole] = mapped_column(
        Enum(GlobalRole, name="global_role"), nullable=False, default=GlobalRole.standard
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.client_id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # When this password was last set -- account creation counts as
    # setting it. Kept as audit information (shown nowhere yet, but
    # useful if this is ever investigated); login() no longer gates on
    # it -- there is no automatic password expiry (NIST SP 800-63B
    # advises against periodic forced rotation; see must_reset_password
    # below for the deliberate, admin-triggered equivalent). No meaning
    # yet for an OAuth-authenticated account (OAuth isn't built -- see
    # PROJECT_BRIEF.md's phasing decision), since there's no password to
    # have changed in the first place.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Set by core/security.py's force_password_reset() (an admin's "force
    # password reset" action) and by invite issuance (an invited account
    # starts with an unusable password hash -- see hash_unusable_password
    # -- so it must never be allowed to log in with a password until one
    # is set). api/auth.py's login() checks this before issuing a
    # session and rejects with the same "use the emailed link" guidance
    # either way; confirm_password_reset clears it once a real password
    # is set.
    must_reset_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Brute-force lockout (core/login_lockout.py). failed_auth_count is
    # incremented by both a wrong password and a wrong 2FA code -- either
    # one is a failed attempt to get past this account's auth, so they
    # share one counter and one lock. last_failed_auth_at is what lets a
    # stale count (an old typo from years ago) not compound with a new
    # one -- see FAILURE_WINDOW. locked_at is NULL when not locked, or the
    # time the lock was set when it is; the lock itself does not expire on
    # its own -- only an admin's unlock action or the user completing a
    # password reset clears it (core/login_lockout.py's clear_failures).
    failed_auth_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_auth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
