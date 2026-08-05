# A numbered "balloon" marker placed on an Image (brief step 2: mark up
# interface points, rendered as numbered red circles with a leader line).
# These are the interface points a later phase (tolerance chain builder)
# links dimension-path components to.
#
# x/y are stored as a fraction (0-1) of the image's natural width/height,
# not raw pixels -- that way a marker's position is independent of
# whatever size the image happens to be displayed at in the browser.

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Marker(Base):
    __tablename__ = "markers"
    __table_args__ = (UniqueConstraint("image_id", "sequence_number"),)

    marker_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.image_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
