# One row of the DIN 16742-style tolerance matrix (e.g. "TG1") -- see
# models/tolerance_value.py for the matrix cells and models/
# dimension_range.py for the columns. Scoped per ProcessType so each
# process (plastics, castings, ...) gets its own independent matrix.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToleranceGroup(Base):
    __tablename__ = "tolerance_groups"
    __table_args__ = (UniqueConstraint("process_type_id", "sequence_number"),)

    tolerance_group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_type_id: Mapped[int] = mapped_column(
        ForeignKey("process_types.process_type_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
