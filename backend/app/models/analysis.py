# An Analysis under a Commodity. `analysis_code` is the human-facing
# unique ID from the brief (commodity code + zero-padded sequence number,
# e.g. "DR-001"). `sequence_number` is stored separately so working out
# "what's the next number for this commodity" is a simple integer query,
# and the unique constraint on it (per commodity) catches any race
# between two analyses being created for the same commodity at once.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("commodity_id", "sequence_number"),)

    analysis_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commodity_id: Mapped[int] = mapped_column(
        ForeignKey("commodities.commodity_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
