# A registered MinIO connection that one or more Projects can be
# assigned to (see models/project.py). Central table, same reasoning as
# models/postgres_service.py.
#
# `secret_key` is never stored in plaintext -- encrypted with
# core/crypto.py before being written here, same as PostgresService's
# password.

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MinioService(Base):
    __tablename__ = "minio_services"

    minio_service_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    access_key: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_secret_key: Mapped[str] = mapped_column(String(500), nullable=False)
    secure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL for a service an admin registered by hand. Set only when
    # core/service_provisioning.py created this bucket and its scoped
    # IAM user itself -- informational only, see PostgresService's
    # matching column.
    provisioned_from_server_id: Mapped[int | None] = mapped_column(
        ForeignKey("minio_servers.minio_server_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
