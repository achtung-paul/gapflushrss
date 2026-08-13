# Login/logout, "who am I", password reset (also used for the first-time
# "set your password" invite link -- see core/invites.py), and the TOTP
# 2FA challenge that can sit between a correct password and an issued
# session (see models/login_challenge.py for why that's a separate
# table rather than a flag on UserSession).

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.security_settings import get_or_create_security_settings
from app.core import totp
from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.email import send_email
from app.core.rate_limit import limiter
from app.core.security import generate_token, hash_password, verify_password
from app.db.session import get_db
from app.models.client import Client
from app.models.login_challenge import CHALLENGE_LIFETIME, MAX_ATTEMPTS, LoginChallenge, LoginChallengeKind
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.models.user_session import SESSION_LIFETIME, UserSession
from app.models.user_totp import UserTotp
from app.schemas.auth import LoginRequest, PasswordResetConfirm, PasswordResetRequest
from app.schemas.two_factor import LoginResult, TwoFactorVerifyRequest
from app.schemas.user import CurrentUserOut

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Shown to the client for both login failures and password-reset requests.
# Not saying *why* it failed stops an attacker using the error message to
# find out which emails exist in the system.
GENERIC_LOGIN_ERROR = "Invalid email or password"
GENERIC_RESET_REQUESTED_MESSAGE = "If that email is registered, a reset link has been sent."
MUST_RESET_PASSWORD_ERROR = "Your password must be reset. Use 'Forgot your password?' to set a new one by email."
CLIENT_INACTIVE_ERROR = "This workspace has been deactivated. Contact your administrator."
INVALID_CODE_ERROR = "Incorrect code."
EXPIRED_CHALLENGE_ERROR = "That login attempt has expired -- please log in again."
TOO_MANY_ATTEMPTS_ERROR = "Too many incorrect codes -- please log in again."

# Hashed once at import. Compared against when the email doesn't match any
# account, so a failed login costs the same bcrypt work either way --
# without this, "no such user" returns in milliseconds while a real
# account takes the full hashing time, which is a reliable way to
# enumerate valid addresses despite the deliberately generic error below.
_TIMING_EQUALIZER_HASH = hash_password("timing-equalizer-not-a-real-password")


def _current_user_out(db: Session, user: User) -> CurrentUserOut:
    # The one place that builds this shape, used by both /login and /me
    # (see CurrentUserOut's docstring) -- so they can never drift into
    # returning different fields for the same user.
    client_name = None
    if user.client_id is not None:
        client = db.get(Client, user.client_id)
        client_name = client.name if client is not None else None
    return CurrentUserOut(
        user_id=user.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        global_role=user.global_role,
        client_id=user.client_id,
        client_name=client_name,
    )


def _issue_session(db: Session, user: User, response: Response) -> CurrentUserOut:
    """The one place a UserSession row (and its cookie) actually gets
    created -- used by both the no-2FA login path and /2fa/verify's
    successful-code path, so a session is never issued any other way.
    """
    session = UserSession(session_token=generate_token(), user_id=user.user_id)
    db.add(session)
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return _current_user_out(db, user)


def _start_verify_challenge(db: Session, user: User) -> LoginResult:
    # User already has a confirmed authenticator -- just need a code
    # from it. No secret to hand back to the client this time.
    challenge = LoginChallenge(
        challenge_token=generate_token(), user_id=user.user_id, kind=LoginChallengeKind.verify
    )
    db.add(challenge)
    db.commit()
    return LoginResult(status="2fa_required", challenge_token=challenge.challenge_token)


def _start_enroll_challenge(db: Session, user: User) -> LoginResult:
    # 2FA is required system-wide but this user has never enrolled --
    # generate a brand-new secret and hold it on the challenge itself,
    # not in user_totp, until a correct code confirms it (see
    # models/login_challenge.py's pending_secret_encrypted comment).
    secret = totp.generate_secret()
    challenge = LoginChallenge(
        challenge_token=generate_token(),
        user_id=user.user_id,
        kind=LoginChallengeKind.enroll,
        pending_secret_encrypted=encrypt_secret(secret),
    )
    db.add(challenge)
    db.commit()

    uri = totp.otpauth_uri(secret, user.email)
    return LoginResult(
        status="enrollment_required",
        challenge_token=challenge.challenge_token,
        otpauth_uri=uri,
        qr_data_uri=totp.qr_code_data_uri(uri),
    )


@router.post("/login", response_model=LoginResult)
@limiter.limit("5/minute")
def login(
    request: Request,  # required by slowapi to identify the caller
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email).first()
    # Always verify against *something*, so the work done is identical
    # whether or not the account exists -- see _TIMING_EQUALIZER_HASH.
    password_ok = verify_password(
        body.password, user.password_hash if user is not None else _TIMING_EQUALIZER_HASH
    )
    if user is None or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    # Checked after the password itself, not before: telling someone who
    # just proved they know the correct password *why* they're being
    # refused doesn't leak anything an attacker could use. An invited
    # account that hasn't set a password yet never reaches here at all --
    # its unusable hash (core/security.py's hash_unusable_password)
    # already fails the check above with the same generic error.
    if user.must_reset_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MUST_RESET_PASSWORD_ERROR)

    # Same reasoning, same ordering: only someone who already proved they
    # know the password is told *why* they're being refused. A
    # deactivated client's admin-forced UserSession cleanup (see
    # api/admin_clients.py) already logs out anyone with an open browser
    # tab -- this is what stops them logging back in afterward.
    if user.client_id is not None:
        client = db.get(Client, user.client_id)
        if client is None or not client.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CLIENT_INACTIVE_ERROR)

    # The 2FA gate -- last check before a session is issued. Reads the
    # one system-wide toggle (default off; see models/security_setting.py)
    # rather than anything per-user, and applies to every account
    # including root_admin.
    security_settings = get_or_create_security_settings(db)
    if security_settings.require_2fa:
        totp_row = db.get(UserTotp, user.user_id)
        if totp_row is None:
            return _start_enroll_challenge(db, user)
        return _start_verify_challenge(db, user)

    return LoginResult(status="ok", user=_issue_session(db, user, response))


@router.post("/2fa/verify", response_model=CurrentUserOut)
@limiter.limit("10/minute")
def verify_2fa(
    request: Request,  # required by slowapi to identify the caller
    body: TwoFactorVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    # A 6-digit TOTP code is only 10**6 possibilities -- this is the one
    # endpoint in the app where rate limiting is load-bearing, not
    # defence in depth. The per-IP limit above stops one attacker from
    # grinding through codes quickly; the per-challenge attempts counter
    # below (MAX_ATTEMPTS) is what stops a *distributed* attacker who
    # already holds a valid challenge_token from routing around the IP
    # limit by spreading guesses across many IPs.
    challenge = db.get(LoginChallenge, body.challenge_token)
    if challenge is None or challenge.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EXPIRED_CHALLENGE_ERROR)

    user = db.get(User, challenge.user_id)
    if user is None:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EXPIRED_CHALLENGE_ERROR)

    if challenge.kind == LoginChallengeKind.enroll:
        secret = decrypt_secret(challenge.pending_secret_encrypted)
        last_used_step = None  # a brand-new secret has never accepted a code
    else:
        totp_row = db.get(UserTotp, user.user_id)
        if totp_row is None:
            # The user's enrollment was reset (e.g. an admin's "reset 2FA"
            # action) in the gap between login() starting this challenge
            # and this request -- there's nothing left to verify against.
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EXPIRED_CHALLENGE_ERROR)
        secret = decrypt_secret(totp_row.secret_encrypted)
        last_used_step = totp_row.last_used_step

    matched_step = totp.verify_code(secret, body.code, last_used_step)
    if matched_step is None:
        challenge.attempts += 1
        if challenge.attempts >= MAX_ATTEMPTS:
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TOO_MANY_ATTEMPTS_ERROR)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_CODE_ERROR)

    if challenge.kind == LoginChallengeKind.enroll:
        # Only written to user_totp now that a real code has confirmed
        # the secret actually works in the user's authenticator app --
        # never on enrollment alone (see models/login_challenge.py).
        db.add(
            UserTotp(
                user_id=user.user_id,
                secret_encrypted=challenge.pending_secret_encrypted,
                last_used_step=matched_step,
            )
        )
    else:
        totp_row.last_used_step = matched_step

    db.delete(challenge)
    return _issue_session(db, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        db.execute(delete(UserSession).where(UserSession.session_token == token))
        db.commit()
    response.delete_cookie(settings.session_cookie_name)


@router.get("/me", response_model=CurrentUserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _current_user_out(db, current_user)


@router.post("/password-reset/request")
@limiter.limit("3/hour")
def request_password_reset(
    request: Request,  # required by slowapi to identify the caller
    body: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email).first()
    if user is not None:
        reset_token = PasswordResetToken(token=generate_token(), user_id=user.user_id)
        db.add(reset_token)
        db.commit()

        reset_link = f"{settings.frontend_origin}/reset-password?token={reset_token.token}"
        try:
            send_email(
                to_address=user.email,
                subject="GapFlush RSS password reset",
                body=f"Reset your password using this link (valid for 1 hour):\n\n{reset_link}",
            )
        except OSError:
            # Don't let an email-delivery problem leak whether the
            # address exists, or crash the request -- just log it.
            logger.exception("Failed to send password reset email")

    return {"message": GENERIC_RESET_REQUESTED_MESSAGE}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    # Handles both an ordinary "forgot password" reset and a first-time
    # invite "set your password" link identically -- the token's
    # `purpose` only changed the email wording and expiry length at
    # creation (see models/password_reset_token.py); once presented here,
    # both mean the same thing: this person now controls the password.
    reset_token = db.get(PasswordResetToken, body.token)
    if (
        reset_token is None
        or reset_token.used
        or reset_token.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.get(User, reset_token.user_id)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    # Clears both an admin's force-password-reset flag and (for an
    # invite token) the state an unusable password hash was already
    # enforcing -- either way, this password now works.
    user.must_reset_password = False
    reset_token.used = True

    # Log the user out everywhere -- a password reset should invalidate
    # any session that might have been started by whoever had the old password.
    db.execute(delete(UserSession).where(UserSession.user_id == user.user_id))

    db.commit()
    return {"message": "Password has been reset. Please log in again."}
