# A numbered "balloon" marker placed on an Image (brief step 2: mark up
# interface points, rendered as numbered red circles with a leader line).
# Each marker IS an Analysis -- dropping one atomically creates its
# Analysis row (see api/images.py's create_marker), and the number shown
# on the balloon is that Analysis's sequence_number, not a column here.
# Deleting a marker deletes its Analysis (and everything under it) --
# see api/images.py's delete_marker.
#
# x/y are stored as a fraction (0-1) of the image's natural width/height,
# not raw pixels -- that way a marker's position is independent of
# whatever size the image happens to be displayed at in the browser.

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Marker(Base):
    __tablename__ = "markers"

    marker_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        ForeignKey("images.image_id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.analysis_id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
