# Creates the first root_admin user on startup, if one doesn't exist yet.
#
# Without this, nobody could ever log in: user accounts are only created
# by a root_admin (via POST /admin/users), but creating the very first
# one needs a root_admin to already exist. Setting ROOT_ADMIN_USERNAME /
# ROOT_ADMIN_EMAIL / ROOT_ADMIN_PASSWORD breaks that chicken-and-egg problem.

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.process_type import ProcessType
from app.models.user import GlobalRole, User

logger = logging.getLogger(__name__)


def create_root_admin_if_needed(db: Session) -> None:
    if not (settings.root_admin_username and settings.root_admin_email and settings.root_admin_password):
        return

    root_admin_exists = (
        db.query(User).filter(User.global_role == GlobalRole.root_admin).first() is not None
    )
    if root_admin_exists:
        return

    db.add(
        User(
            username=settings.root_admin_username,
            email=settings.root_admin_email,
            password_hash=hash_password(settings.root_admin_password),
            global_role=GlobalRole.root_admin,
        )
    )
    db.commit()
    logger.info("Created initial root_admin user %r", settings.root_admin_username)


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
