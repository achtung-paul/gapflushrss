# Password hashing and random token generation.
#
# We never store a user's actual password -- only a bcrypt hash of it.
# bcrypt automatically includes a random "salt" in the hash it produces,
# so two users with the same password still get different hashes.

import secrets
from datetime import datetime, timezone

import bcrypt
from sqlalchemy.orm import Session

from app.core.breached_passwords import is_commonly_breached
from app.models.user import User
from app.models.user_session import UserSession

MIN_PASSWORD_LENGTH = 12

# bcrypt hashes at most 72 bytes and *silently ignores* anything beyond
# that -- a 100-character passphrase is really only its first 72 bytes,
# with no error to tell you. Rejecting over-long passwords outright makes
# that limit visible instead of quietly weakening the password.
MAX_PASSWORD_BYTES = 72


def validate_password_strength(value: str) -> str:
    """Shared password rule for account creation and password reset.

    Raises ValueError (not HTTPException) so it can be used directly as a
    pydantic field_validator -- FastAPI turns that into a 422 with the
    message attached.

    Deliberately no composition rule (no forced upper/lower/digit/symbol)
    -- NIST SP 800-63B advises against those, since in practice they push
    users toward predictable variants of the same password rather than
    genuinely stronger ones. Length plus a common-password check is the
    recommended replacement; see core/breached_passwords.py.
    """
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    # Byte length, not character count: a 72-character string containing
    # any non-ASCII character is more than 72 bytes once encoded.
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    if is_commonly_breached(value):
        # Deliberately generic -- naming the wordlist just tells an
        # attacker which variants to try next.
        raise ValueError("this password is too common -- please choose a different one")
    return value


def hash_password(plain_password: str) -> str:
    hashed_bytes = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token() -> str:
    # Used for session tokens, password-reset tokens, invite tokens, and
    # 2FA login-challenge tokens. 32 random bytes, URL-safe encoded --
    # unguessable and safe to put in a URL.
    return secrets.token_urlsafe(32)


def hash_unusable_password() -> str:
    """A structurally valid bcrypt hash that no real password will ever
    match -- used for an invited account that hasn't set a password yet.

    Deliberately not "" or a fixed placeholder string: verify_password
    calls bcrypt.checkpw() on whatever is stored, and bcrypt raises
    ValueError (not just "returns False") on a malformed hash -- storing
    "" would turn a login attempt against a not-yet-activated account
    into an unhandled 500 instead of the ordinary wrong-password 401.
    Hashing a fresh random token keeps the column a real bcrypt hash, so
    every existing code path that reads password_hash needs no special
    case for "this account hasn't set one yet".
    """
    return hash_password(secrets.token_urlsafe(32))


def force_password_reset(db: Session, user: User) -> None:
    """Make a user's current password stop working, without knowing it.

    Sets an explicit flag rather than backdating password_changed_at --
    that trick only worked while login() enforced a rolling password
    expiry (see the deleted PASSWORD_EXPIRY). Without an expiry check to
    trip, backdating the timestamp would be a silent no-op: the button
    would appear to work in the admin UI while leaving the account fully
    usable. must_reset_password is login()'s own explicit gate instead.
    Sessions are killed too, so an already-open browser doesn't keep
    working with the old password. Caller is responsible for the commit
    (both call sites already have other changes to commit in the same
    transaction).
    """
    user.must_reset_password = True
    db.query(UserSession).filter(UserSession.user_id == user.user_id).delete()
