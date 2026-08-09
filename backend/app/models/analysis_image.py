# Reference photos attached directly to a Gap or Flush entry -- a plain
# gallery, distinct from the Commodity's single annotated assembly image
# with markers (see models/image.py, models/marker.py). An entry can have
# any number of these. File bytes live in MinIO under `object_key`, same
# storage helpers as Commodity images (see core/service_storage.py).
#
# Scoped to the entry, not the Analysis -- Gap and Flush get their own
# separate gallery even though both hang off the same Analysis, since a
# gap photo and a flush photo are rarely the same picture. (Originally
# this was analysis_id-scoped and shared between Gap/Flush; see the
# migration that moved it to entry_id for the backfill rule used on
# already-uploaded images.)

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class AnalysisImage(ProjectBase):
    __tablename__ = "analysis_images"

    analysis_image_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_entries.entry_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
