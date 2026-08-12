# A MinIO *server* the app has administrative (root) rights on --
# distinct from MinioService (models/minio_service.py), which represents
# one specific, already-existing bucket plus its own scoped access
# credentials. Registering a MinioServer is what makes it possible to
# auto-provision a brand-new bucket, with its own dedicated IAM user
# scoped to just that bucket, for a client at creation time
# (core/service_provisioning.py) -- root_access_key/encrypted_root_secret_key
# must be MinIO's actual root/admin identity (able to run `mc admin user
# add` / `mc admin policy` operations), not a scoped per-bucket key.
#
# Registered once, reused for many clients: the root credentials stored
# here never become a MinioService's own credentials -- each provisioned
# client gets a freshly generated, bucket-scoped access key instead.

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MinioServer(Base):
    __tablename__ = "minio_servers"

    minio_server_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    secure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    root_access_key: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_root_secret_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
