# Login/logout, "who am I", and password reset.

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.email import send_email
from app.core.security import generate_token, hash_password, verify_password
from app.db.session import get_db
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.models.user_session import SESSION_LIFETIME, UserSession
from app.schemas.auth import LoginRequest, PasswordResetConfirm, PasswordResetRequest
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Shown to the client for both login failures and password-reset requests.
# Not saying *why* it failed stops an attacker using the error message to
# find out which usernames/emails exist in the system.
GENERIC_LOGIN_ERROR = "Invalid username or password"
GENERIC_RESET_REQUESTED_MESSAGE = "If that email is registered, a reset link has been sent."
PASSWORD_EXPIRED_ERROR = "Your password has expired. Use 'Forgot your password?' to reset it by email."

# Password-based accounts have to reset every 30 days. Only applies to
# password auth -- there's no OAuth login in this codebase yet (see
# PROJECT_BRIEF.md's phasing decision), so every account is a password
# account today; an OAuth account should skip this check once that's built.
PASSWORD_EXPIRY = timedelta(days=30)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    # Checked after the password itself, not before: telling someone who
    # just proved they know the correct password that it's specifically
    # *expired* (rather than the generic wrong-password error) doesn't
    # leak anything an attacker could use.
    if datetime.now(timezone.utc) - user.password_changed_at > PASSWORD_EXPIRY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_EXPIRED_ERROR)

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
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        db.execute(delete(UserSession).where(UserSession.session_token == token))
        db.commit()
    response.delete_cookie(settings.session_cookie_name)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/password-reset/request")
def request_password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is not None:
        reset_token = PasswordResetToken(token=generate_token(), user_id=user.user_id)
        db.add(reset_token)
        db.commit()

        reset_link = f"{settings.frontend_origin}/reset-password?token={reset_token.token}"
        try:
            send_email(
                to_address=user.email,
                subject="GapFlushRSS password reset",
                body=f"Reset your password using this link (valid for 1 hour):\n\n{reset_link}",
            )
        except OSError:
            # Don't let an email-delivery problem leak whether the
            # address exists, or crash the request -- just log it.
            logger.exception("Failed to send password reset email")

    return {"message": GENERIC_RESET_REQUESTED_MESSAGE}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
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
    reset_token.used = True

    # Log the user out everywhere -- a password reset should invalidate
    # any session that might have been started by whoever had the old password.
    db.execute(delete(UserSession).where(UserSession.user_id == user.user_id))

    db.commit()
    return {"message": "Password has been reset. Please log in again."}
