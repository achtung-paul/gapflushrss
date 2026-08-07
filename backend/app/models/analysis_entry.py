# A Gap or Flush entry attached to an Analysis (brief: "-GAP" / "-FLUSH"
# suffix on the Analysis's unique ID). Gap and Flush have identical
# fields, so rather than two near-duplicate tables this is one table with
# an `entry_type` column, plus a unique constraint so an Analysis can have
# at most one Gap and one Flush.
#
# nominal/upper_limit/lower_limit use Numeric (fixed-point), not float,
# so tolerance values like 0.5mm don't pick up binary floating-point
# rounding error.
#
# The full display ID (e.g. "DR-001-GAP") isn't stored here -- it's just
# analysis.analysis_code + "-" + entry_type, built when needed (see
# api/analyses.py) instead of duplicating data that could go stale.

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class EntryType(str, enum.Enum):
    GAP = "GAP"
    FLUSH = "FLUSH"


class Direction(str, enum.Enum):
    X = "X"
    Y = "Y"
    Z = "Z"
    OTHER = "OTHER"


class AnalysisEntry(ProjectBase):
    __tablename__ = "analysis_entries"
    __table_args__ = (UniqueConstraint("analysis_id", "entry_type"),)

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.analysis_id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType, name="entry_type"), nullable=False)

    # Which vehicle coordinate axis this Gap/Flush is measured along --
    # blank until set, same as every other optional field here.
    direction: Mapped[Direction | None] = mapped_column(Enum(Direction, name="direction"), nullable=True)

    # e.g. nominal=3.5, upper_limit=1, lower_limit=0.2 means the
    # acceptable band is 3.3 to 4.5 (nominal - lower_limit to
    # nominal + upper_limit). Limits are stored as positive magnitudes.
    nominal_value: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    upper_limit: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    lower_limit: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Plain name snapshots, not FKs -- this table lives on a per-project
    # Postgres service, while User rows live in the central database, so
    # a real foreign key/join across services isn't possible (same
    # reasoning as StandardTolerance.updated_by_name).
    created_by_name: Mapped[str] = mapped_column(String(201), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(201), nullable=False)
