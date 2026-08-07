# Resolves a PostgresService row (models/postgres_service.py) into an
# actual SQLAlchemy connection, and manages the project-scoped Alembic
# chain (alembic_project/ -- Commodity and everything under it) against
# whichever service is being addressed.
#
# Engines are cached per service rather than built fresh on every
# request -- each one holds its own connection pool, and there's no
# reason to reconnect on every call. The cache is a plain module-level
# dict: fine for one backend worker process (see CLAUDE.md), would need
# a lock if this app ever ran multiple workers concurrently.

from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.crypto import decrypt_secret
from app.models.postgres_service import PostgresService

# .../backend, however this process was started -- so alembic_project's
# files resolve the same way whether we're in the container's /app or a
# local checkout, regardless of the caller's current working directory.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Must match alembic_project/env.py's VERSION_TABLE -- this is the table
# whose mere existence means "this database has been initialized with
# the project schema at least once".
VERSION_TABLE = "alembic_version_project"

# Matches alembic_project/versions/0ab50047e838_initial_project_schema.py's
# revision id -- what a *legacy* database (see initialize_schema below)
# gets stamped at, since its tables already match that revision's shape
# (once the constraint fixes below are applied) without ever running it.
PROJECT_HEAD_REVISION = "0ab50047e838"

ServiceStatus = Literal["unreachable", "not_initialized", "initialized"]

_engine_cache: dict[int, Engine] = {}
_sessionmaker_cache: dict[int, sessionmaker] = {}


def _database_url(service: PostgresService) -> str:
    password = decrypt_secret(service.encrypted_password)
    return (
        f"postgresql+psycopg2://{service.username}:{password}"
        f"@{service.host}:{service.port}/{service.database}"
    )


def get_engine(service: PostgresService) -> Engine:
    if service.postgres_service_id not in _engine_cache:
        _engine_cache[service.postgres_service_id] = create_engine(_database_url(service))
    return _engine_cache[service.postgres_service_id]


def get_session(service: PostgresService) -> Session:
    if service.postgres_service_id not in _sessionmaker_cache:
        _sessionmaker_cache[service.postgres_service_id] = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine(service)
        )
    return _sessionmaker_cache[service.postgres_service_id]()


def evict(service: PostgresService) -> None:
    # Called when a service's credentials could no longer be valid to
    # reuse -- currently just on delete, so a stale cached engine isn't
    # kept around pointing at a service the admin removed.
    engine = _engine_cache.pop(service.postgres_service_id, None)
    _sessionmaker_cache.pop(service.postgres_service_id, None)
    if engine is not None:
        engine.dispose()


def check_status(service: PostgresService) -> ServiceStatus:
    try:
        engine = get_engine(service)
        with engine.connect() as connection:
            initialized = inspect(connection).has_table(VERSION_TABLE)
    except Exception:
        # Any failure here (wrong password, host unreachable, DB doesn't
        # exist, ...) means the same thing to an admin looking at the
        # services list: this connection doesn't work right now. The
        # specific reason isn't actionable from this status check alone.
        return "unreachable"
    return "initialized" if initialized else "not_initialized"


def _project_alembic_config(url: str) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic_project.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic_project"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def initialize_schema(service: PostgresService) -> None:
    url = _database_url(service)
    engine = get_engine(service)

    with engine.connect() as connection:
        inspector = inspect(connection)
        is_legacy = inspector.has_table("commodities") and not inspector.has_table(VERSION_TABLE)

    if is_legacy:
        # The "Default" service created by the one-time migration to
        # multi-service support (alembic/versions/fe5a0c40a1ce_*.py)
        # already has commodities/analyses/etc -- they were created by
        # this app's original, single Alembic chain, back before the
        # project-scoped chain (alembic_project/) existed. Record
        # "already at that chain's starting revision" without re-running
        # CREATE TABLE (which would fail -- the tables are already
        # there), then bring the two constraints that revision actually
        # defines in line with how this database currently has them.
        #
        # This runs as plain application code (not from inside a running
        # migration) deliberately -- an earlier version tried driving
        # this from inside the central migration itself, and nesting a
        # second Alembic EnvironmentContext inside an already-active one
        # corrupted the outer migration's `op` proxy. Keeping this call
        # stack flat avoids that.
        #
        # Constraint fixes run *before* the stamp, not after: command.stamp
        # commits on its own connection independently of anything else in
        # this function, so if it ran first and the ALTER statements then
        # failed, check_status (which only checks whether the version
        # table exists) would report "initialized" on a database that
        # never actually got the fix -- with no way to detect or retry it.
        # Doing the fixes first means a failure here leaves the version
        # table unwritten, so a retry is still possible.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE commodities DROP CONSTRAINT IF EXISTS commodities_project_id_fkey")
            )
            connection.execute(
                text("ALTER TABLE commodities DROP CONSTRAINT IF EXISTS commodities_code_key")
            )
            connection.execute(
                text(
                    "ALTER TABLE commodities ADD CONSTRAINT commodities_project_id_code_key "
                    "UNIQUE (project_id, code)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE chain_components DROP CONSTRAINT IF EXISTS "
                    "chain_components_tolerance_value_id_fkey"
                )
            )
        command.stamp(_project_alembic_config(url), PROJECT_HEAD_REVISION)
    else:
        # `alembic upgrade head` is idempotent, so this same call also
        # serves as "bring an already-initialized service's schema up to
        # date" if the project chain grows new migrations later -- not
        # just first-time setup.
        command.upgrade(_project_alembic_config(url), "head")
