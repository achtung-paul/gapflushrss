# Password hashing and random token generation.
#
# We never store a user's actual password -- only a bcrypt hash of it.
# bcrypt automatically includes a random "salt" in the hash it produces,
# so two users with the same password still get different hashes.

import secrets

import bcrypt

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
    """
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    # Byte length, not character count: a 72-character string containing
    # any non-ASCII character is more than 72 bytes once encoded.
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return value


def hash_password(plain_password: str) -> str:
    hashed_bytes = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token() -> str:
    # Used for both session tokens and password-reset tokens. 32 random
    # bytes, URL-safe encoded -- unguessable and safe to put in a URL.
    return secrets.token_urlsafe(32)
