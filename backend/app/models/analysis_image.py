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

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


# Set at upload time (api/analysis_images.py's upload_analysis_image
# defaults new images to other), changeable afterwards via the tag-only
# PATCH route. sketch_agreed gets special treatment: list_analysis_images
# and export_entry (api/exports.py) both sort it to the front of the
# gallery, ahead of everything else, regardless of upload order.
#
# Member names deliberately lowercase, matching their own values exactly
# (same convention as BannerColour/LoginChallengeKind/GlobalRole) -- a
# name/value mismatch here broke SQL-side enum comparisons (`.filter(...)`
# in api/analysis_images.py's _tag_ordered binds by the enum member's
# .name, not .value, so e.g. SKETCH_AGREED="sketch_agreed" would try to
# insert the literal string "SKETCH_AGREED" into the Postgres enum and
# fail with InvalidTextRepresentation). Every other enum in this codebase
# avoids the bug by keeping name == value; don't reintroduce a mismatch.
class ImageTag(str, enum.Enum):
    sketch_proposal = "sketch_proposal"
    sketch_agreed = "sketch_agreed"
    other = "other"


class AnalysisImage(ProjectBase):
    __tablename__ = "analysis_images"

    analysis_image_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_entries.entry_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tag: Mapped[ImageTag] = mapped_column(
        Enum(ImageTag, name="image_tag"), nullable=False, server_default=ImageTag.other.value
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
