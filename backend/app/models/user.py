# The Users table from PROJECT_BRIEF.md: Users(user_id, username, global_role).
# We also store email (needed for password-reset emails) and password_hash.
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
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    global_role: Mapped[GlobalRole] = mapped_column(
        Enum(GlobalRole, name="global_role"), nullable=False, default=GlobalRole.standard
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
