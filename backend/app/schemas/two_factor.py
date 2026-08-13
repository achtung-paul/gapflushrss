# Request/response shapes for the 2FA login gate -- api/auth.py's
# login() and its /auth/2fa/verify endpoint.

from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.user import CurrentUserOut


class LoginResult(BaseModel):
    """What POST /auth/login returns -- one of three shapes, driven by
    `status`, depending on whether 2FA is required and whether this user
    has already enrolled:

      "ok"                   -- password (and 2FA, if already required)
                                 succeeded outright; `user` is set and a
                                 session cookie has been issued.
      "2fa_required"         -- password was correct; a code from the
                                 user's already-enrolled authenticator is
                                 needed next via /auth/2fa/verify. No
                                 session cookie yet.
      "enrollment_required"  -- password was correct, but this user has
                                 never enrolled a TOTP secret.
                                 otpauth_uri/qr_data_uri describe a
                                 *brand new* secret that is not saved
                                 anywhere until confirmed via
                                 /auth/2fa/verify. No session cookie yet.
    """

    status: Literal["ok", "2fa_required", "enrollment_required"]
    user: CurrentUserOut | None = None
    challenge_token: str | None = None
    otpauth_uri: str | None = None
    qr_data_uri: str | None = None


class TwoFactorVerifyRequest(BaseModel):
    challenge_token: str
    code: str

    @field_validator("code")
    @classmethod
    def code_must_be_six_digits(cls, value: str) -> str:
        # Authenticator apps sometimes render the code with a space in
        # the middle ("123 456") -- strip before checking shape, so a
        # copy-paste from the app doesn't fail validation on whitespace
        # alone.
        stripped = value.strip().replace(" ", "")
        if not stripped.isdigit() or len(stripped) != 6:
            raise ValueError("code must be 6 digits")
        return stripped
