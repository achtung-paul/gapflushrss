# The Users table. Login is by email + password (see api/auth.py) --
# there's no separate username. first_name/last_name are what's shown
# everywhere a person needs to be identified (header, admin user list,
# project member list, "last modified by" columns) instead.
#
# global_role only distinguishes "root_admin" (bypasses all project-scope
# checks, per the brief) from "standard". Everything else -- what a user
# can do inside a specific project -- comes from which Group they belong
# to in that project (see UserGroupProject in group.py), never from a
# role stored directly on the user.

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GlobalRole(str, enum.Enum):
    root_admin = "root_admin"
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # When this password was last set -- account creation counts as
    # setting it. api/auth.py's login() compares this against
    # PASSWORD_EXPIRY to force a reset after 30 days; password-reset
    # confirm is the only other place that updates it. No meaning yet
    # for an OAuth-authenticated account (OAuth isn't built -- see
    # PROJECT_BRIEF.md's phasing decision), since there's no password to
    # expire in the first place.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
