# The half-authenticated state between "password was correct" and "2FA
# code was correct" (see api/auth.py's login() and its /auth/2fa/verify
# endpoint).
#
# Deliberately its own table rather than a "pending" flag on
# UserSession: api/deps.py's get_current_user grants full access on the
# session cookie alone, with no other check layered on top anywhere in
# the app. Putting the half-authenticated state on UserSession would
# mean every route -- present and future -- would need to remember to
# check that flag, and missing it even once would let someone in after
# only the password step. A separate table makes that impossible by
# construction: no UserSession row is ever created until the 2FA step
# actually succeeds (or 2FA is off).

import enum
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Short-lived on purpose -- long enough to open an authenticator app and
# type a code, short enough that a challenge left dangling (browser tab
# closed mid-login) doesn't sit around as a usable object for long.
CHALLENGE_LIFETIME = timedelta(minutes=5)

# How many wrong codes a single challenge tolerates before it's deleted,
# forcing the user back to a fresh password login. A 6-digit TOTP code is
# only 10**6 possibilities -- this cap, together with /auth/2fa/verify's
# own per-IP rate limit (core/rate_limit.py), is what makes brute-forcing
# it impractical; the IP limit alone isn't enough, since a distributed
# attacker holding one valid challenge token could otherwise spread
# guesses across many IPs.
MAX_ATTEMPTS = 5


class LoginChallengeKind(str, enum.Enum):
    verify = "verify"  # user already has a confirmed TOTP secret
    enroll = "enroll"  # user has none yet -- must confirm a new one


class LoginChallenge(Base):
    __tablename__ = "login_challenges"

    challenge_token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    kind: Mapped[LoginChallengeKind] = mapped_column(
        Enum(LoginChallengeKind, name="login_challenge_kind"), nullable=False
    )
    # Only set for kind == enroll: the secret being enrolled, held here
    # (encrypted, same as UserTotp.secret_encrypted) until a correct code
    # confirms it. Never written to user_totp until that confirmation --
    # so an enrollment nobody finished (challenge expired, or the QR was
    # never scanned) never leaves a live-but-unconfirmed secret behind.
    pending_secret_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + CHALLENGE_LIFETIME,
    )
