# Sends plain-text emails (password-reset and account-invite links). Two
# providers, selected by settings.email_provider:
#
#   "smtp" (dev/test default) -- talks to Mailhog, a fake SMTP server that
#   just captures emails so you can view them at http://<host>:8025
#   instead of needing a real mail account (see docker-compose.yml).
#
#   "resend" (preprod/production, see docs/PREPROD_DEPLOY.md) -- posts
#   to Resend's REST API instead. No relay to run, and no SMTP
#   credentials to protect in transit -- the request is HTTPS straight to
#   Resend.
#
# Every caller of send_email uses `except OSError` to turn a delivery
# failure into a clean error without crashing the request (api/auth.py's
# request_password_reset, and every send_account_invite call site in
# api/admin.py, api/admin_clients.py, api/client_admin.py) -- both
# providers below only ever raise OSError (or a subclass) on failure, so
# that catch keeps working unchanged no matter which provider is
# configured.

import logging
import smtplib
from email.message import EmailMessage

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# smtplib and requests both default to no timeout at all, which means a
# mail server or Resend itself accepting the connection and then going
# quiet blocks *forever*. send_email is called synchronously from inside a
# request handler, so a stalled send holds a worker thread indefinitely --
# enough of them and the API stops responding. Ten seconds is generous for
# either an SMTP handshake or an HTTPS round-trip.
EMAIL_TIMEOUT_SECONDS = 10

SMTP_INSECURE_AUTH_MESSAGE = (
    "SMTP_USERNAME is set but SMTP_USE_TLS is not -- refusing to send SMTP credentials "
    "over an unencrypted connection. Set SMTP_USE_TLS=true, or clear SMTP_USERNAME if "
    "the relay doesn't need authentication."
)

RESEND_SEND_URL = "https://api.resend.com/emails"


def validate_email_settings() -> None:
    """Fail fast at startup on an email config that can't work.

    Called from main.py's lifespan. Checking here rather than only at send
    time means the misconfiguration surfaces immediately on deploy, in the
    logs, instead of the first time a user happens to request a password
    reset.
    """
    if settings.email_provider == "resend":
        if not settings.resend_api_key:
            raise RuntimeError(
                "email_provider is 'resend' but RESEND_API_KEY is not set."
            )
        return
    if settings.smtp_username and not settings.smtp_use_tls:
        raise RuntimeError(SMTP_INSECURE_AUTH_MESSAGE)


def send_email(to_address: str, subject: str, body: str) -> None:
    if settings.email_provider == "resend":
        _send_via_resend(to_address, subject, body)
    else:
        _send_via_smtp(to_address, subject, body)


def _send_via_resend(to_address: str, subject: str, body: str) -> None:
    # requests' own exceptions (ConnectionError, Timeout, HTTPError, ...)
    # all subclass OSError -- see the module docstring above for why that
    # matters to every caller of send_email. No wrapping needed here.
    response = requests.post(
        RESEND_SEND_URL,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Accept": "application/json",
        },
        json={
            "from": settings.email_from_address,
            "to": to_address,
            "subject": subject,
            "text": body,
        },
        timeout=EMAIL_TIMEOUT_SECONDS,
    )
    # Unlike Postmark, Resend never reports a failure inside a 200 body --
    # a bad API key, an unverified sending domain, or a rejected recipient
    # all come back as a non-2xx status with a JSON error body, so
    # raise_for_status() alone is enough to make every failure mode visible
    # to send_email's callers via the OSError contract described above.
    response.raise_for_status()


def _send_via_smtp(to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.email_from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=EMAIL_TIMEOUT_SECONDS
    ) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            # Refuse to authenticate over an unencrypted connection: SMTP
            # AUTH sends the username and password as base64, which is
            # plaintext to anyone on the path. Without this guard, setting
            # SMTP_USERNAME while forgetting SMTP_USE_TLS would leak the
            # mail account's credentials on every password-reset email,
            # silently. Failing loudly is the safe direction -- same
            # reasoning as the sslmode=require rule in core/service_db.py.
            #
            # Raised as an SMTPException (which subclasses OSError) rather
            # than a bare RuntimeError so every caller's existing
            # `except OSError` catches and reports it. If it escaped as a
            # 500, the password-reset endpoint would answer 500 for a
            # registered address and 200 for an unregistered one --
            # handing back exactly the account enumeration that its
            # generic response message exists to prevent.
            # validate_email_settings() above is what makes this loud, at
            # startup, where it can't leak anything.
            if not settings.smtp_use_tls:
                raise smtplib.SMTPException(SMTP_INSECURE_AUTH_MESSAGE)
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
