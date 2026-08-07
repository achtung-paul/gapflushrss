# Request/response shapes for the /auth routes. Pydantic validates
# incoming JSON against these automatically -- e.g. a login request
# missing "password" gets rejected with a 422 before our code even runs.

from pydantic import BaseModel, EmailStr, field_validator

from app.core.security import validate_password_strength


class LoginRequest(BaseModel):
    email: EmailStr
    # Deliberately unvalidated: this is checking an *existing* password,
    # so applying the strength rule here would reject logins from accounts
    # created before that rule existed (and leak the rule to attackers).
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        # Same rule as account creation -- see core/security.py.
        return validate_password_strength(value)
