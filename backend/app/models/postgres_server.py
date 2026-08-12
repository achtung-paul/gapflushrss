# A Postgres *server* the app has administrative rights on -- distinct
# from PostgresService (models/postgres_service.py), which represents one
# specific, already-existing database plus its own connection credentials.
# A PostgresServer is what makes it possible to *create* a new database on
# demand (api/admin_clients.py's create_client, when auto-provisioning
# rather than picking an existing PostgresService) -- the admin_username
# stored here must have CREATEDB and CREATEROLE privileges on the server,
# not just SELECT/INSERT rights on one database.
#
# Registered once, reused for many clients: each auto-provisioned client
# gets its own dedicated database and its own dedicated login role on this
# same physical server (core/service_provisioning.py), never the admin
# credentials stored here directly -- those never leave this table.

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostgresServer(Base):
    __tablename__ = "postgres_servers"

    postgres_server_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    # Must be able to CREATE ROLE and CREATE DATABASE on this server --
    # a stronger privilege than any single PostgresService's own username
    # needs, so this is deliberately a separate, more powerful credential,
    # stored and used only by the provisioning path.
    admin_username: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_admin_password: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
