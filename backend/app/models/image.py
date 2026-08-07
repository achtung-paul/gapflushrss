# An image uploaded against a Commodity (brief step 2: "upload an image
# of the part/assembly") -- one shared assembly photo, annotated with
# markers that each represent one Analysis (see models/marker.py). The
# actual file bytes live in MinIO under `object_key`; this row is just
# the metadata pointing at it.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class Image(ProjectBase):
    __tablename__ = "images"

    image_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commodity_id: Mapped[int] = mapped_column(
        ForeignKey("commodities.commodity_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
