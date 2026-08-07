# Reference photos attached directly to an Analysis -- a plain gallery,
# distinct from the Commodity's single annotated assembly image with
# markers (see models/image.py, models/marker.py). An Analysis can have
# any number of these. File bytes live in MinIO under `object_key`, same
# storage helpers as Commodity images (see core/storage.py).

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisImage(Base):
    __tablename__ = "analysis_images"

    analysis_image_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.analysis_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
