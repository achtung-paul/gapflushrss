# A Client is one SaaS tenant: a sandbox holding its own users, projects,
# and reference data (the tolerance matrix), invisible to every other
# client and to root_admin.
#
# Isolation is by dedicated infrastructure, not just a WHERE clause --
# root admin assigns each client exactly one Postgres service and one
# MinIO service, and a service is never assigned to more than one client
# (enforced in api/admin_clients.py, not by a DB constraint, since
# "in use" depends on whether any Client row already references it).
# Projects inherit both from their client (see models/project.py) -- a
# client admin never picks a service, because they can't see the list.

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"

    client_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    postgres_service_id: Mapped[int] = mapped_column(
        ForeignKey("postgres_services.postgres_service_id"), nullable=False
    )
    minio_service_id: Mapped[int] = mapped_column(
        ForeignKey("minio_services.minio_service_id"), nullable=False
    )
    # Deactivating blocks login for every user of this client (api/auth.py)
    # and kills their live sessions immediately (api/admin_clients.py) --
    # the non-destructive lever for a lapsed subscription. Deleting a
    # client is a separate, snapshotted purge (see DELETE /admin/clients).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
