# The generic "process type -> tolerance class -> value" table from the
# brief. Deliberately empty/generic for now -- real DIN 16742/16901
# figures get loaded into this later; we don't invent values.
#
# ondelete="CASCADE": deleting a ProcessType removes its tolerance
# classes too, instead of leaving orphaned rows behind.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToleranceClass(Base):
    __tablename__ = "tolerance_classes"
    __table_args__ = (UniqueConstraint("process_type_id", "class_name"),)

    tolerance_class_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_type_id: Mapped[int] = mapped_column(
        ForeignKey("process_types.process_type_id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
