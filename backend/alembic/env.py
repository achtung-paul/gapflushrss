# Alembic's migration runner. This mostly follows Alembic's standard
# generated template, with two project-specific changes:
# 1. The database URL comes from app settings, not alembic.ini, so
#    connection details only live in one place.
# 2. target_metadata points at our shared Base, so `alembic revision
#    --autogenerate` can see every model that inherits from it.

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base

# Import models so Base.metadata knows about every table before Alembic
# compares it against the database (needed for --autogenerate).
import app.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Guarded for the same reason as alembic_project/env.py -- see the longer
# note there. This chain only runs from the command line today (the
# Dockerfile's `alembic upgrade head`), so the guard is a no-op here, but
# it keeps both chains behaving the same if this one is ever driven from
# inside the app too.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
