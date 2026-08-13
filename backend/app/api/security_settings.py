# The system-wide 2FA toggle (see models/security_setting.py for why
# it's a single row). Root admin only, in both directions -- unlike
# banner.py's split GET (any user) / PUT (root admin), there is no
# *public* read here: /auth/login's own response already tells a
# logging-in user everything they need (whether a code or an enrollment
# is required), so a separate "am I required to use 2FA?" endpoint would
# just be a second, easier-to-forget-to-check source of the same answer.
# The GET below exists only so the admin settings page can show the
# current value before it's changed -- it's still root-admin-only, same
# as the PUT.

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.core.security_events import EVENT_SECURITY_SETTINGS_CHANGED, record_event
from app.db.session import get_db
from app.models.security_setting import SECURITY_SETTINGS_ID, SecuritySetting
from app.models.user import User
from app.schemas.security_setting import SecuritySettingOut, SecuritySettingUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


def get_or_create_security_settings(db: Session) -> SecuritySetting:
    """The one security-settings row, created with 2FA off on first
    access. Created here rather than seeded by the migration so there's
    no ordering dependency, and so a deployment whose row was somehow
    deleted recovers to the safe default (off) instead of 500ing.

    Exported (not module-private) -- api/auth.py's login() needs to read
    require_2fa on every login attempt, and duplicating this
    get-or-create logic there would risk the two copies drifting.
    """
    row = db.get(SecuritySetting, SECURITY_SETTINGS_ID)
    if row is None:
        row = SecuritySetting(
            security_settings_id=SECURITY_SETTINGS_ID, require_2fa=False, updated_by_name=""
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/security-settings", response_model=SecuritySettingOut)
def read_security_settings(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    return get_or_create_security_settings(db)


@router.put("/security-settings", response_model=SecuritySettingOut)
def update_security_settings(
    request: Request,
    body: SecuritySettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
):
    row = get_or_create_security_settings(db)
    old_value = row.require_2fa
    row.require_2fa = body.require_2fa
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by_name = f"{current_user.first_name} {current_user.last_name}"
    if old_value != body.require_2fa:
        # System-wide, not per-client -- this is the one event type in
        # the whole table with no client_id, the same way the setting
        # itself has no per-client override (see models/security_setting.py).
        record_event(
            db,
            event_type=EVENT_SECURITY_SETTINGS_CHANGED,
            actor=current_user,
            request=request,
            detail=f"require_2fa -> {body.require_2fa}",
        )
    db.commit()
    db.refresh(row)
    return row
