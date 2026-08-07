# Request/response shapes for the /auth routes. Pydantic validates
# incoming JSON against these automatically -- e.g. a login request
# missing "password" gets rejected with a 422 before our code even runs.

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
