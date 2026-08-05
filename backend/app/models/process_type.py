# Admin-editable list of manufacturing process types (plastics, castings,
# pressings, ...). v1 only ever seeds "Plastics" (see core/bootstrap.py),
# but the table exists so more can be added later with no schema change.

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessType(Base):
    __tablename__ = "process_types"

    process_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
