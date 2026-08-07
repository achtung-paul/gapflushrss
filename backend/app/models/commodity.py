# Commodity(name, code) under a Project, per PROJECT_BRIEF.md's data
# hierarchy: Project -> Commodity -> Analysis. `code` is the 2-letter
# prefix (e.g. "DR" for Doors) used to build each Analysis's unique ID --
# unique per project, not system-wide, so it's scoped by (project_id, code).
#
# This table lives on whichever Postgres service the parent Project is
# assigned to (see core/service_db.py), not the app's own central
# database where the Project row itself lives -- so `project_id` is a
# plain column, not a real ForeignKey (Postgres can't enforce a FK across
# two separate databases). Two projects can be colocated on the same
# physical service, so every query against this table must filter by
# project_id explicitly, not just by primary key -- see api/analyses.py's
# _get_commodity_or_404 and friends.

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class Commodity(ProjectBase):
    __tablename__ = "commodities"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    commodity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
