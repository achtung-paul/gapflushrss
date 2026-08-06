# One cell of the DIN 16742-style tolerance matrix: the intersection of
# a ToleranceGroup (row) and a DimensionRange (column). tool_value and
# non_tool_value are the tool-specific (T) and non-tool-specific (NT)
# symmetric +/- deviations from the standard's table -- a group doesn't
# always define both (e.g. some groups only ever use one of the two),
# so both are nullable.
#
# A blank cell in the matrix (the standard's "-") is represented by
# there being no row at all for that group/range pair, rather than a
# row with both values null -- see api/reference_data.py's upsert
# endpoint, which deletes the row if both values come back empty.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToleranceValue(Base):
    __tablename__ = "tolerance_values"
    __table_args__ = (UniqueConstraint("tolerance_group_id", "dimension_range_id"),)

    tolerance_value_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tolerance_group_id: Mapped[int] = mapped_column(
        ForeignKey("tolerance_groups.tolerance_group_id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension_range_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_ranges.dimension_range_id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_value: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    non_tool_value: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
