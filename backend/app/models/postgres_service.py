# A registered Postgres connection that one or more Projects can be
# assigned to (see models/project.py). Central table -- lives in the
# app's own fixed database alongside Users/Projects/Groups, never on a
# per-project service itself.
#
# `password` is never stored in plaintext -- it's encrypted with
# core/crypto.py before being written here, and decrypted only when
# actually opening a connection (core/service_db.py).

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostgresService(Base):
    __tablename__ = "postgres_services"

    postgres_service_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    database: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(String(500), nullable=False)
    # NULL for a service an admin registered by hand (pointing at a
    # database that already existed). Set only when
    # core/service_provisioning.py created this service's database and
    # role itself -- purely informational (which PostgresServer this came
    # from), nothing reads it to make a decision.
    provisioned_from_server_id: Mapped[int | None] = mapped_column(
        ForeignKey("postgres_servers.postgres_server_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
