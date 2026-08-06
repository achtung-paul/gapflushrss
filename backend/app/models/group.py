# Groups and project membership, matching the DB shape from PROJECT_BRIEF.md:
#   Groups(group_id, group_name)
#   User_Group_Project(user_id, group_id, project_id)
#
# A Group row on its own doesn't know which project it belongs to -- that
# link only exists through UserGroupProject rows. In practice, every group
# is auto-created for exactly one project (see api/admin.py), with a name
# like "Project-Doors-Managers", so it only ever appears in
# UserGroupProject rows for that one project.
#
# Permissions are never stored directly on a User -- only by which group
# they're a member of, in which project (per the brief: "Permissions are
# never assigned directly to users -- only via project-scoped groups").

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The three group "kinds" auto-created for every new project, and what
# each is allowed to do. Used to build the group_name (e.g.
# "Project-Doors-Managers") and to decide what a member of that group can do.
MANAGERS = "Managers"  # read / write / delete
CONTRIBUTORS = "Contributors"  # read / write
VIEWERS = "Viewers"  # read-only


class Group(Base):
    __tablename__ = "groups"

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class UserGroupProject(Base):
    __tablename__ = "user_group_project"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.group_id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True
    )
