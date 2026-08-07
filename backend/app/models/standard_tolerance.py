# A project's own named tolerance presets (e.g. "Locator" = +/-0.1mm),
# maintained by that project's Managers and offered as a quick pick-from
# option when building a chain component (see api/chain_components.py),
# alongside the separate, global, root-admin-only DIN tolerance matrix
# (models/tolerance_value.py). Unlike that matrix, this is per-project,
# not process-type-based, and anyone who can view the project can use
# it -- only adding/editing/deleting is Manager-only.
#
# This table lives on whichever Postgres service the parent Project is
# assigned to (see core/service_db.py), same as models/commodity.py --
# so `project_id` is a plain column, not a real ForeignKey, and every
# query against this table must filter by project_id explicitly.
#
# `updated_by_name` is a plain string snapshot (the user's first + last
# name at the time) of whoever last created/changed the row, not a
# foreign key to Users -- User is a central-database model, this table
# isn't, so there's no way to enforce or live-join a real FK here (same
# reasoning as ChainComponent.tolerance_value_id's provenance-only
# reference).

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class StandardTolerance(ProjectBase):
    __tablename__ = "standard_tolerances"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    standard_tolerance_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Symmetric +/- magnitude in mm, same shape as ChainComponent.tolerance_value.
    tolerance_value: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(201), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
