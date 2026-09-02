# Per-account brute-force lockout, shared by the password step and the
# 2FA step of login (see api/auth.py's login() and verify_2fa()).
#
# Pure DB-level helpers, no Request/HTTPException here -- the same shape
# as core/security.py's force_password_reset() -- so callers decide what
# to tell the client and this module stays testable without going
# through FastAPI's dependency injection.

from datetime import datetime, timedelta, timezone

from app.models.user import User

# How many failed attempts (wrong password OR wrong 2FA code, counted
# together) lock the account.
MAX_FAILURES = 10

# A failure older than this doesn't count towards the total -- without a
# window, ten scattered mistypes over a couple of years would eventually
# lock a real account for no reason. The lock itself, once set, does NOT
# expire on its own (see models/user.py's locked_at) -- only this window
# applies to the counter that leads up to it.
FAILURE_WINDOW = timedelta(minutes=15)


def is_locked(user: User) -> bool:
    return user.locked_at is not None


def register_failure(db, user: User) -> bool:
    """Record one failed auth attempt for this user. Returns True if this
    particular failure is the one that locked the account.

    No-op if the account is already locked -- there's nothing more
    informative to count once locked_at is set, and doing so would just
    push last_failed_auth_at forward for no reason.
    """
    if is_locked(user):
        return False

    now = datetime.now(timezone.utc)
    stale = user.last_failed_auth_at is None or (now - user.last_failed_auth_at) > FAILURE_WINDOW
    user.failed_auth_count = 1 if stale else user.failed_auth_count + 1
    user.last_failed_auth_at = now

    if user.failed_auth_count >= MAX_FAILURES:
        user.locked_at = now
        return True
    return False


def clear_failures(db, user: User) -> None:
    """Reset the counter and lift any lock -- called on a successful
    login and on a completed password reset (the self-service recovery
    path), plus every admin "unlock" route.
    """
    user.failed_auth_count = 0
    user.last_failed_auth_at = None
    user.locked_at = None
