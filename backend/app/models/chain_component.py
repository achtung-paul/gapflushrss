# One contributor in a Gap/Flush entry's tolerance chain (brief step 4:
# "trace the dimension path... input component tolerances... account for
# assembly variation"). Component tolerances (GD&T-based) and assembly
# process variation (robotic placement, fixture, locator, fastening
# shift, ...) are the same shape of data -- just a ± tolerance value --
# so they live in one table with a `contributor_type` column rather than
# two near-duplicate tables (same reasoning as AnalysisEntry's
# gap/flush `entry_type`).
#
# tolerance_value is a single symmetric ± magnitude (not asymmetric
# upper/lower like AnalysisEntry) -- that's the standard shape for RSS
# stack-up inputs, and it's what the user confirmed for this feature.
#
# tolerance_class_id is optional provenance only: if the value was
# prefilled from the admin reference table (Phase 3), we record which
# class it came from, but tolerance_value is still its own snapshotted
# column so a later edit to the class doesn't silently change a saved
# analysis.

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContributorType(str, enum.Enum):
    COMPONENT = "COMPONENT"
    PROCESS = "PROCESS"


class ChainComponent(Base):
    __tablename__ = "chain_components"
    __table_args__ = (UniqueConstraint("entry_id", "sequence_number"),)

    chain_component_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_entries.entry_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    contributor_type: Mapped[ContributorType] = mapped_column(
        Enum(ContributorType, name="contributor_type"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    tolerance_value: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    tolerance_class_id: Mapped[int | None] = mapped_column(
        ForeignKey("tolerance_classes.tolerance_class_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
