# Writes and prunes the security_events audit trail (models/security_event.py).
# One entry point in, record_event(), used from every route listed in the
# plan behind this feature -- auth, permission changes, user/client
# lifecycle, data deletion, and Excel exports.

import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limit import client_ip
from app.models.security_event import SECURITY_EVENT_RETENTION, SecurityEvent
from app.models.user import User

logger = logging.getLogger(__name__)

# --- event_type constants ---------------------------------------------
# Written here, never as a hand-typed string at a call site -- a typo in
# a literal would silently create a new, never-filtered-for event_type;
# a typo in a name here is an ImportError instead.

EVENT_LOGIN_SUCCESS = "auth.login_success"
EVENT_LOGIN_FAILED = "auth.login_failed"
EVENT_LOGIN_BLOCKED = "auth.login_blocked"
EVENT_LOGIN_RATE_LIMITED = "auth.rate_limited"
EVENT_ACCOUNT_LOCKED = "auth.account_locked"
EVENT_LOGOUT = "auth.logout"
EVENT_2FA_ENROLLED = "auth.2fa_enrolled"
EVENT_2FA_FAILED = "auth.2fa_failed"
EVENT_2FA_LOCKED = "auth.2fa_locked"
EVENT_PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
EVENT_PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"

EVENT_USER_CREATED = "user.created"
EVENT_USER_DELETED = "user.deleted"
EVENT_USER_ROLE_CHANGED = "user.role_changed"
EVENT_USER_PASSWORD_RESET_FORCED = "user.password_reset_forced"
EVENT_USER_2FA_RESET = "user.2fa_reset"
EVENT_USER_UNLOCKED = "user.unlocked"
EVENT_USER_INVITE_RESENT = "user.invite_resent"
EVENT_PROJECT_MEMBER_ADDED = "user.project_member_added"
EVENT_PROJECT_MEMBER_REMOVED = "user.project_member_removed"

EVENT_CLIENT_CREATED = "client.created"
EVENT_CLIENT_DELETED = "client.deleted"
EVENT_CLIENT_ACTIVATED = "client.activated"
EVENT_CLIENT_DEACTIVATED = "client.deactivated"

EVENT_PROJECT_CREATED = "project.created"
EVENT_PROJECT_DELETED = "project.deleted"

EVENT_SECURITY_SETTINGS_CHANGED = "system.security_settings_changed"

EVENT_DATA_DELETED = "data.deleted"

EVENT_EXPORT_ENTRY = "export.entry_excel"
EVENT_EXPORT_COMMODITY = "export.commodity_excel"


def record_event(
    db: Session,
    *,
    event_type: str,
    outcome: str = "success",
    actor: User | None = None,
    actor_email: str | None = None,
    request: Request | None = None,
    client_id: int | None = None,
    client_name: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    target_name: str | None = None,
    detail: str | None = None,
) -> None:
    """Record one row to the security event log.

    Adds to `db` but deliberately does NOT commit -- the caller's own
    commit (already happening for the action this event describes) writes
    the two together in one transaction, so an event can never be recorded
    for an action that didn't actually happen, or vice versa. The one
    exception is a handful of auth failure paths that have no other write
    to piggyback on; those call db.commit() themselves right after.

    Never raises. A bug in audit logging must not be able to block a
    login, a delete, or anything else it's merely observing -- a missing
    row is a much smaller problem than a 500 on every login. Any failure
    is swallowed and reported through the ordinary operational logger
    instead (core/logging_config.py), which is a completely separate,
    shorter-retention channel from this table.
    """
    try:
        actor_user_id = actor.user_id if actor is not None else None
        resolved_email = actor.email if actor is not None else (actor_email or "")
        resolved_name = f"{actor.first_name} {actor.last_name}" if actor is not None else ""
        resolved_role = actor.global_role.value if actor is not None else None
        resolved_client_id = client_id if client_id is not None else (actor.client_id if actor is not None else None)
        resolved_ip = client_ip(request) if request is not None else None

        db.add(
            SecurityEvent(
                event_type=event_type,
                outcome=outcome,
                actor_user_id=actor_user_id,
                actor_email=resolved_email,
                actor_name=resolved_name,
                actor_role=resolved_role,
                client_id=resolved_client_id,
                client_name=client_name,
                source_ip=resolved_ip,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                detail=detail,
            )
        )
    except Exception:
        logger.exception("Failed to record security event %r", event_type)


def cleanup_old_security_events(db: Session) -> int:
    """Delete every event older than SECURITY_EVENT_RETENTION_DAYS.

    Called from main.py's daily sweep, alongside (but independently of)
    core/logging_config.py's cleanup_old_logs() -- the two retention
    periods are different on purpose (7 days of operational noise vs. 360
    days of security-relevant history) and must stay that way; see
    models/security_event.py's SECURITY_EVENT_RETENTION_DAYS.
    """
    cutoff = datetime.now(timezone.utc) - SECURITY_EVENT_RETENTION
    removed = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.occurred_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed
