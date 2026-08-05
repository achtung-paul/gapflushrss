# A logged-in session. On login we create one of these rows and give the
# browser its session_token as an HttpOnly cookie; on every request after
# that we look the token up here to find out who's making the request.
# Logging out (or a password reset) just deletes the row(s).
#
# This is a plain database-backed session, not a JWT. That keeps the auth
# code simple: no signing keys, no token-expiry math to get right in two
# places -- "is this session valid?" is one query.

from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SESSION_LIFETIME = timedelta(days=7)


class UserSession(Base):
    __tablename__ = "user_sessions"

    session_token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + SESSION_LIFETIME,
    )
