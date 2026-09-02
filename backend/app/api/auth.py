# Login/logout, "who am I", password reset (also used for the first-time
# "set your password" invite link -- see core/invites.py), and the TOTP
# 2FA challenge that can sit between a correct password and an issued
# session (see models/login_challenge.py for why that's a separate
# table rather than a flag on UserSession).

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.security_settings import get_or_create_security_settings
from app.core import totp
from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.email import send_email
from app.core.login_lockout import clear_failures, is_locked, register_failure
from app.core.rate_limit import limiter
from app.core.security import generate_token, hash_password, verify_password
from app.core.security_events import (
    EVENT_2FA_ENROLLED,
    EVENT_2FA_FAILED,
    EVENT_2FA_LOCKED,
    EVENT_ACCOUNT_LOCKED,
    EVENT_LOGIN_BLOCKED,
    EVENT_LOGIN_FAILED,
    EVENT_LOGIN_SUCCESS,
    EVENT_LOGOUT,
    EVENT_PASSWORD_RESET_COMPLETED,
    EVENT_PASSWORD_RESET_REQUESTED,
    record_event,
)
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
ACCOUNT_LOCKED_ERROR = (
    "This account has been locked after too many failed sign-in attempts. "
    "Contact your administrator, or use 'Forgot your password?' to unlock it by email."
)

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


def _issue_session(db: Session, user: User, response: Response, request: Request) -> CurrentUserOut:
    """The one place a UserSession row (and its cookie) actually gets
    created -- used by both the no-2FA login path and /2fa/verify's
    successful-code path, so a session is never issued any other way.
    Also the one place a successful login is recorded, for the same
    reason: whichever path got here (with or without 2FA), the meaningful
    security event is "this account is now logged in".
    """
    session = UserSession(session_token=generate_token(), user_id=user.user_id)
    db.add(session)
    # A real login clears any accumulated failures -- covers both the
    # no-2FA path and 2fa/verify's successful-code path in one place.
    clear_failures(db, user)
    record_event(db, event_type=EVENT_LOGIN_SUCCESS, actor=user, request=request)
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
        # actor_email, not actor -- there is no confirmed account here,
        # only an attempted address, and that's exactly what an incident
        # investigation needs to see (which addresses were being tried).
        # Its own commit: this branch raises immediately, with nothing
        # else in this request to piggyback the write onto.
        record_event(
            db, event_type=EVENT_LOGIN_FAILED, outcome="failure", actor_email=body.email, request=request
        )
        # A wrong password against a real account counts towards that
        # account's lockout -- an unknown email has no row to count
        # against, so this is a no-op there (and doesn't reveal which
        # case it was; the response is identical either way).
        if user is not None and register_failure(db, user):
            record_event(db, event_type=EVENT_ACCOUNT_LOCKED, outcome="failure", actor=user, request=request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    # Only reachable with a *correct* password, so naming the lock here
    # doesn't leak anything an attacker without the password could use --
    # same reasoning as must_reset_password/client_inactive below. Checked
    # first, before either of those, so a locked account never reaches
    # the 2FA gate and can no longer mint a fresh challenge to grind
    # through (see core/login_lockout.py).
    if is_locked(user):
        record_event(
            db, event_type=EVENT_LOGIN_BLOCKED, outcome="failure", actor=user, request=request,
            detail="account_locked",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCOUNT_LOCKED_ERROR)

    # Checked after the password itself, not before: telling someone who
    # just proved they know the correct password *why* they're being
    # refused doesn't leak anything an attacker could use. An invited
    # account that hasn't set a password yet never reaches here at all --
    # its unusable hash (core/security.py's hash_unusable_password)
    # already fails the check above with the same generic error.
    if user.must_reset_password:
        record_event(
            db,
            event_type=EVENT_LOGIN_BLOCKED,
            outcome="failure",
            actor=user,
            request=request,
            detail="must_reset_password",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MUST_RESET_PASSWORD_ERROR)

    # Same reasoning, same ordering: only someone who already proved they
    # know the password is told *why* they're being refused. A
    # deactivated client's admin-forced UserSession cleanup (see
    # api/admin_clients.py) already logs out anyone with an open browser
    # tab -- this is what stops them logging back in afterward.
    if user.client_id is not None:
        client = db.get(Client, user.client_id)
        if client is None or not client.is_active:
            record_event(
                db,
                event_type=EVENT_LOGIN_BLOCKED,
                outcome="failure",
                actor=user,
                request=request,
                detail="client_inactive",
            )
            db.commit()
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

    return LoginResult(status="ok", user=_issue_session(db, user, response, request))


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
    # below (MAX_ATTEMPTS) stops one held challenge_token from being
    # brute-forced past 5 guesses. Neither of those alone stops a
    # distributed attacker who already knows the password from just
    # calling /login again for a fresh challenge with a clean attempts
    # counter -- register_failure()'s account-wide lockout below
    # (core/login_lockout.py) is what closes that gap, since it persists
    # across however many challenges get minted.
    challenge = db.get(LoginChallenge, body.challenge_token)
    if challenge is None or challenge.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EXPIRED_CHALLENGE_ERROR)

    user = db.get(User, challenge.user_id)
    if user is None:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EXPIRED_CHALLENGE_ERROR)

    # The account could have been locked (by an admin, or by a parallel
    # /login attempt registering the failure that tips it over) in the
    # gap between this challenge being issued and this request arriving.
    if is_locked(user):
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCOUNT_LOCKED_ERROR)

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
        # Counts towards the account-wide lockout too, not just this
        # challenge's own MAX_ATTEMPTS -- see the comment above on why
        # that's what stops a distributed attacker from just minting a
        # fresh challenge per 5 guesses. Checked first: a failure severe
        # enough to lock the account supersedes the ordinary
        # "too many attempts on this challenge" outcome below.
        if register_failure(db, user):
            record_event(db, event_type=EVENT_ACCOUNT_LOCKED, outcome="failure", actor=user, request=request)
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ACCOUNT_LOCKED_ERROR)
        if challenge.attempts >= MAX_ATTEMPTS:
            record_event(db, event_type=EVENT_2FA_LOCKED, outcome="failure", actor=user, request=request)
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TOO_MANY_ATTEMPTS_ERROR)
        record_event(db, event_type=EVENT_2FA_FAILED, outcome="failure", actor=user, request=request)
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
        record_event(db, event_type=EVENT_2FA_ENROLLED, actor=user, request=request)
    else:
        totp_row.last_used_step = matched_step

    db.delete(challenge)
    return _issue_session(db, user, response, request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        # Looked up before deleting, purely so the event below can name
        # who logged out -- the delete itself doesn't need this.
        session = db.get(UserSession, token)
        if session is not None:
            user = db.get(User, session.user_id)
            record_event(db, event_type=EVENT_LOGOUT, actor=user, request=request)
        db.execute(delete(UserSession).where(UserSession.session_token == token))
        db.commit()
    response.delete_cookie(settings.session_cookie_name)


@router.get("/me", response_model=CurrentUserOut)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _current_user_out(db, current_user)


def _send_password_reset_email(to_address: str, reset_link: str) -> None:
    # Run via BackgroundTasks, after the response has already gone out --
    # see request_password_reset's comment on why. Its own try/except
    # since a route's exception handling can no longer catch anything
    # raised after the response is sent.
    try:
        send_email(
            to_address=to_address,
            subject="StackFit Pro password reset",
            body=f"Reset your password using this link (valid for 1 hour):\n\n{reset_link}",
        )
    except OSError:
        logger.exception("Failed to send password reset email")


@router.post("/password-reset/request")
@limiter.limit("3/hour")
def request_password_reset(
    request: Request,  # required by slowapi to identify the caller
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # send_email is a blocking network call (core/email.py) -- up to
    # EMAIL_TIMEOUT_SECONDS. Done only when the account exists, that
    # turned this endpoint's response time itself into an account-
    # enumeration channel despite the generic message below, unlike
    # login() which deliberately equalizes (_TIMING_EQUALIZER_HASH
    # above). Deferring the send to run after the response is returned
    # closes that gap -- both branches now return in about the time of
    # one DB query, whether or not the address exists.
    user = db.query(User).filter(User.email == body.email).first()
    if user is not None:
        reset_token = PasswordResetToken(token=generate_token(), user_id=user.user_id)
        db.add(reset_token)
        record_event(db, event_type=EVENT_PASSWORD_RESET_REQUESTED, actor=user, request=request)
        db.commit()

        reset_link = f"{settings.frontend_origin}/reset-password?token={reset_token.token}"
        background_tasks.add_task(_send_password_reset_email, user.email, reset_link)

    return {"message": GENERIC_RESET_REQUESTED_MESSAGE}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
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
    # Self-service recovery from a lockout: completing a reset proves
    # control of the mailbox, which is exactly what the attacker who
    # triggered the lock doesn't have (core/login_lockout.py).
    clear_failures(db, user)

    # Log the user out everywhere -- a password reset should invalidate
    # any session that might have been started by whoever had the old password.
    db.execute(delete(UserSession).where(UserSession.user_id == user.user_id))

    record_event(db, event_type=EVENT_PASSWORD_RESET_COMPLETED, actor=user, request=request)
    db.commit()
    return {"message": "Password has been reset. Please log in again."}
