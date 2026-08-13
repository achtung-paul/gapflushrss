# One column of the tolerance matrix (e.g. "> 3 to 6"
# mm) -- see models/tolerance_value.py for the matrix cells and models/
# tolerance_group.py for the rows. Scoped per ProcessType, same as
# ToleranceGroup.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DimensionRange(Base):
    __tablename__ = "dimension_ranges"
    __table_args__ = (UniqueConstraint("process_type_id", "sequence_number"),)

    dimension_range_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_type_id: Mapped[int] = mapped_column(
        ForeignKey("process_types.process_type_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    min_value: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    # Nullable -- a NULL max_value means "and above", an open-ended top
    # range (some tolerance standards' last row/column has no upper
    # bound, e.g. "over 10"). Every reader of this column (the CSV
    # importer, the tolerance-chain range matcher, the matrix UI) has to
    # treat None as "no upper limit", not as missing data.
    max_value: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
