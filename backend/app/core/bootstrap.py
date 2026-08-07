# Creates the first root_admin user on startup, if one doesn't exist yet.
#
# Without this, nobody could ever log in: user accounts are only created
# by a root_admin (via POST /admin/users), but creating the very first
# one needs a root_admin to already exist. Setting ROOT_ADMIN_FIRST_NAME /
# ROOT_ADMIN_LAST_NAME / ROOT_ADMIN_EMAIL / ROOT_ADMIN_PASSWORD breaks
# that chicken-and-egg problem.

import logging

from sqlalchemy.orm import Session

from app.core import service_db
from app.core.config import settings
from app.core.security import hash_password
from app.models.postgres_service import PostgresService
from app.models.process_type import ProcessType
from app.models.user import GlobalRole, User

logger = logging.getLogger(__name__)


def create_root_admin_if_needed(db: Session) -> None:
    if not (
        settings.root_admin_first_name
        and settings.root_admin_last_name
        and settings.root_admin_email
        and settings.root_admin_password
    ):
        return

    root_admin_exists = (
        db.query(User).filter(User.global_role == GlobalRole.root_admin).first() is not None
    )
    if root_admin_exists:
        return

    db.add(
        User(
            first_name=settings.root_admin_first_name,
            last_name=settings.root_admin_last_name,
            email=settings.root_admin_email,
            password_hash=hash_password(settings.root_admin_password),
            global_role=GlobalRole.root_admin,
        )
    )
    db.commit()
    logger.info("Created initial root_admin user %r", settings.root_admin_email)


def create_default_process_types_if_needed(db: Session) -> None:
    # v1 scope is plastics only (per the brief) -- the process type list
    # itself is admin-editable from here on, this just seeds that one
    # starting entry so the app isn't empty on first run.
    any_process_type_exists = db.query(ProcessType).first() is not None
    if any_process_type_exists:
        return

    db.add(ProcessType(name="Plastics"))
    db.commit()
    logger.info("Seeded default process type 'Plastics'")


def adopt_default_service_if_needed(db: Session) -> None:
    # The "Default" PostgresService (seeded by
    # alembic/versions/fe5a0c40a1ce_multi_service_postgres_minio.py's
    # one-time migration) already has commodities/analyses/etc -- they're
    # this app's original data, created back before Commodity-and-below
    # moved to its own Alembic chain (alembic_project/). Running this on
    # every startup, rather than waiting for an admin to click
    # "Initialize" on it, means an upgrade from the old single-database
    # world keeps working immediately with no manual step. Harmless to
    # call repeatedly -- initialize_schema no-ops once this service is
    # no longer "legacy" (see its docstring).
    default_service = db.query(PostgresService).filter(PostgresService.name == "Default").first()
    if default_service is None:
        return

    if service_db.check_status(default_service) == "not_initialized":
        service_db.initialize_schema(default_service)
        logger.info("Adopted the Default Postgres service into the project-scoped Alembic chain")


def upgrade_initialized_services(db: Session) -> None:
    # The project-scoped chain (alembic_project/) has no single fixed
    # database, so it can't run from the Dockerfile's startup command the
    # way the central chain does -- it has to be applied once per service.
    # Previously that meant an admin clicking "Initialize" on every service
    # after every deploy that added a project-chain migration, and
    # forgetting simply left the schema stale: the failure showed up later
    # as an UndefinedColumn error on an ordinary request, with nothing
    # pointing back at the missed migration.
    #
    # Doing it here makes deploys self-applying. initialize_schema ends in
    # `alembic upgrade head`, which is idempotent, so this is a no-op for
    # services that are already current.
    #
    # Failures are logged and skipped rather than raised: one unreachable
    # service must not stop the app from starting. Anything skipped here
    # can still be brought up to date later with the admin Initialize
    # button, or on the next restart.
    for service in db.query(PostgresService).all():
        try:
            if service_db.check_status(service) != "initialized":
                continue
            service_db.initialize_schema(service)
            logger.info("Project schema is up to date on Postgres service %r", service.name)
        except Exception:
            logger.exception(
                "Could not upgrade the project schema on Postgres service %r -- skipping it. "
                "Use the admin Initialize button once it's reachable again.",
                service.name,
            )
