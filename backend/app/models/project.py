from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    # Two clients may legitimately both have a project called "Doors" --
    # project names are only unique within a client, not globally, now
    # that clients exist.
    __table_args__ = (UniqueConstraint("client_id", "project_name", name="uq_projects_client_id_project_name"),)

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Which Client's sandbox this project belongs to. Not null -- a
    # project always belongs to exactly one client, unlike User.client_id
    # which is nullable for root_admin. Every project-scoped route
    # ultimately checks this against the caller's own client_id (see
    # api/deps.py's get_project) before returning anything.
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.client_id"), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Which Postgres/MinIO this project's Commodity-and-below data lives
    # on (see core/service_db.py, core/service_storage.py) -- copied from
    # the owning Client at creation and never changed, since moving a
    # live project to a different physical service would mean copying
    # all its data, which isn't supported. Both point at central rows
    # (models/postgres_service.py, models/minio_service.py), so a normal
    # FK is fine here even though the project's *own* data (Commodity and
    # below) can no longer have real FKs back to this table -- see
    # models/commodity.py.
    postgres_service_id: Mapped[int] = mapped_column(
        ForeignKey("postgres_services.postgres_service_id"), nullable=False
    )
    minio_service_id: Mapped[int] = mapped_column(
        ForeignKey("minio_services.minio_service_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
