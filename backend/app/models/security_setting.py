# The one system-wide security toggle: whether every user must use TOTP
# 2FA to log in. Root-admin-owned (see api/security_settings.py), and
# applies to every account including root_admin itself -- there is no
# per-client override and no exemption list.
#
# Deliberately a single row rather than per-client rows (contrast
# models/statistical_model_setting.py, which really is per-client) -- 2FA
# enforcement is a property of the whole deployment, not something one
# tenant should be able to turn off for itself. Modelled on
# models/banner.py's fixed-id singleton: no "which one is current?"
# query, no way to end up with two conflicting settings rows, and
# api/security_settings.py creates it on first access rather than the
# migration seeding it, so there's no ordering dependency and a
# hand-deleted row recovers on its own.

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The fixed primary key of the one and only security-settings row.
SECURITY_SETTINGS_ID = 1


class SecuritySetting(Base):
    __tablename__ = "security_settings"

    security_settings_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Default False: 2FA is fully built but opt-in for a deployment,
    # turned on later by a root admin (see api/security_settings.py).
    # When True, api/auth.py's login() demands a TOTP code from every
    # user -- enrolling on the spot if they haven't already (see
    # models/user_totp.py, models/login_challenge.py).
    require_2fa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_by_name: Mapped[str] = mapped_column(String(201), nullable=False, server_default="")
