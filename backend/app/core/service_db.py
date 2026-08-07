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

from app.core.config import settings
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
#
# This is the chain's FIRST revision, not its head. Stamping it only says
# "you are at the starting point"; initialize_schema still has to run an
# upgrade afterwards to pull the database the rest of the way. It was
# previously named PROJECT_HEAD_REVISION, which read as though stamping it
# were sufficient -- it isn't, and the mismatch left adopted databases
# several migrations behind while check_status still reported them as
# "initialized".
PROJECT_INITIAL_REVISION = "0ab50047e838"

ServiceStatus = Literal["unreachable", "not_initialized", "initialized"]

_engine_cache: dict[int, Engine] = {}
_sessionmaker_cache: dict[int, sessionmaker] = {}


# How long to wait for a TCP connection before giving up. Without this,
# an unreachable service blocks for the OS-level timeout (minutes) --
# which matters because check_status runs on every services-list request
# and bootstrap.upgrade_initialized_services probes every service on
# startup.
CONNECT_TIMEOUT_SECONDS = 5


def _database_url(service: PostgresService) -> str:
    password = decrypt_secret(service.encrypted_password)

    # The bundled Postgres (settings.postgres_host) runs without TLS, and
    # sits on the host-local docker bridge where there's no network hop to
    # intercept -- so it stays on libpq's default opportunistic mode. Every
    # *other* registered service is genuinely remote, and libpq's "prefer"
    # would silently fall back to plaintext if that server didn't offer
    # TLS, sending its credentials in the clear with nothing to signal it.
    # "require" refuses to connect instead, which fails loudly at Initialize
    # time -- the safe direction.
    #
    # Comparing against settings.postgres_host is exact rather than a
    # hostname guess: that name is precisely how the bundled container is
    # addressed on the compose network.
    sslmode = "prefer" if service.host == settings.postgres_host else "require"

    return (
        f"postgresql+psycopg2://{service.username}:{password}"
        f"@{service.host}:{service.port}/{service.database}"
        f"?sslmode={sslmode}&connect_timeout={CONNECT_TIMEOUT_SECONDS}"
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
    # Stops alembic_project/env.py calling fileConfig(), which would
    # reconfigure logging for the whole process: it disables every
    # existing logger and replaces the root handlers with the ones from
    # the .ini. Running inside the app -- which this always is -- that
    # silently killed all application and uvicorn logging from the first
    # schema upgrade onwards. See the note in that env.py.
    cfg.attributes["configure_logger"] = False
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
            # Guarded rather than a bare ADD CONSTRAINT: Postgres has no
            # "ADD CONSTRAINT IF NOT EXISTS", and every other statement in
            # this block is already idempotent. Without the guard a retry
            # after a partial failure dies here with DuplicateTable --
            # which would contradict the whole point of the ordering noted
            # above, since the retry the comment promises wouldn't work.
            connection.execute(
                text(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS ("
                    "SELECT 1 FROM pg_constraint "
                    "WHERE conname = 'commodities_project_id_code_key'"
                    ") THEN "
                    "ALTER TABLE commodities ADD CONSTRAINT commodities_project_id_code_key "
                    "UNIQUE (project_id, code); "
                    "END IF; END $$;"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE chain_components DROP CONSTRAINT IF EXISTS "
                    "chain_components_tolerance_value_id_fkey"
                )
            )
        command.stamp(_project_alembic_config(url), PROJECT_INITIAL_REVISION)

    # Always upgrade to head, including straight after the stamp above.
    # The stamp only records "this database matches the chain's *first*
    # revision" -- every migration added since then still has to run, or
    # the database would sit silently out of date while check_status (which
    # only looks for the version table) reported it as initialized.
    #
    # `alembic upgrade head` is idempotent, so this same call also serves as
    # "bring an already-initialized service up to date" when the project
    # chain grows new migrations later -- which is how
    # bootstrap.upgrade_initialized_services uses it.
    command.upgrade(_project_alembic_config(url), "head")
