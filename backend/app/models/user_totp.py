# One row per user who has completed TOTP enrollment. No row here means
# "not enrolled" -- api/auth.py's login() checks for a row's absence to
# decide whether to demand a fresh enrollment or an ordinary code.
#
# user_id is both the primary key and the FK: a user has at most one
# TOTP secret, ever. Re-enrolling (e.g. after core/security.py's
# 2FA-reset action deletes this row) always produces a brand-new secret
# rather than reusing or reactivating an old one.

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserTotp(Base):
    __tablename__ = "user_totp"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    # Encrypted at rest with core/crypto.py's Fernet helpers (the same
    # ones used for stored Postgres/MinIO service credentials) -- unlike
    # a password, we have to get the plaintext secret back out again to
    # verify a code against it, so it can't be hashed the way
    # password_hash is.
    secret_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # The RFC 6238 time step of the last code this user's account
    # accepted -- core/totp.py's verify_code() refuses to accept a code
    # for a step at or before this one, so a code can't be replayed a
    # second time inside its own ~30-second validity window. Nullable
    # only because the column has to have *some* value before the very
    # first successful verification; every row created after enrollment
    # succeeds gets a real one immediately.
    last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
