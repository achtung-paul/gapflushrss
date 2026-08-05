# Password hashing and random token generation.
#
# We never store a user's actual password -- only a bcrypt hash of it.
# bcrypt automatically includes a random "salt" in the hash it produces,
# so two users with the same password still get different hashes.

import secrets

import bcrypt


def hash_password(plain_password: str) -> str:
    hashed_bytes = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_token() -> str:
    # Used for both session tokens and password-reset tokens. 32 random
    # bytes, URL-safe encoded -- unguessable and safe to put in a URL.
    return secrets.token_urlsafe(32)
