# Client-admin-editable list of manufacturing process types (plastics,
# castings, pressings, ...). Every new Client is seeded with "Plastics"
# at creation time (see api/admin_clients.py) -- v1 scope is plastics
# only, per the brief, but the table exists so more can be added later
# with no schema change.
#
# Reference data is per-client now: ToleranceGroup, DimensionRange and
# ToleranceValue all cascade from a ProcessType (ondelete="CASCADE" all
# the way down), so putting client_id here alone scopes the whole
# tolerance matrix without needing the column on every table underneath.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessType(Base):
    __tablename__ = "process_types"
    __table_args__ = (UniqueConstraint("client_id", "name", name="uq_process_types_client_id_name"),)

    process_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.client_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
