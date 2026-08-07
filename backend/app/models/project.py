# Minimal Project model for Phase 1 -- just enough to test that creating a
# project auto-creates its three groups (see api/admin.py). Full Project
# CRUD, and the Commodity/Analysis tables underneath it, are built out in
# Phase 2.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Which Postgres/MinIO this project's Commodity-and-below data lives
    # on (see core/service_db.py, core/service_storage.py) -- set once at
    # creation and never changed, since moving a live project to a
    # different physical service would mean copying all its data, which
    # isn't supported. Both point at central rows (models/postgres_service.py,
    # models/minio_service.py), so a normal FK is fine here even though
    # the project's *own* data (Commodity and below) can no longer have
    # real FKs back to this table -- see models/commodity.py.
    postgres_service_id: Mapped[int] = mapped_column(
        ForeignKey("postgres_services.postgres_service_id"), nullable=False
    )
    minio_service_id: Mapped[int] = mapped_column(
        ForeignKey("minio_services.minio_service_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
