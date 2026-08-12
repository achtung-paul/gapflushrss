# Groups and project membership, evolved from the DB shape sketched in
# PROJECT_BRIEF.md (Groups(group_id, group_name), User_Group_Project(...)).
#
# A group is identified by (project_id, role_name) -- a real FK to Project,
# not a name string. Earlier this was found by rebuilding a display string
# like "Project-Doors-Managers" and looking that up, which meant renaming a
# project had to remember to rewrite all three group names by hand or every
# member silently lost access. That's gone now: the FK cascades on project
# delete, and a rename touches nothing here at all.
#
# Permissions are never stored directly on a User -- only by which group
# they're a member of, in which project (per the brief: "Permissions are
# never assigned directly to users -- only via project-scoped groups").

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The three group "kinds" auto-created for every new project, and what
# each is allowed to do -- these are the only valid values of role_name.
MANAGERS = "Managers"  # read / write / delete
CONTRIBUTORS = "Contributors"  # read / write
VIEWERS = "Viewers"  # read-only


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("project_id", "role_name", name="uq_groups_project_id_role_name"),)

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One of MANAGERS / CONTRIBUTORS / VIEWERS above.
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)


class UserGroupProject(Base):
    __tablename__ = "user_group_project"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.group_id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True
    )
