# Sends plain-text emails over SMTP (used for password-reset links).
#
# In dev/test (see docker-compose.yml), this points at Mailhog: a fake SMTP
# server that just captures emails so you can view them in a browser at
# http://<host>:8025 instead of needing a real mail account. Production
# deployment (Phase 9) points these same settings at a real SMTP relay --
# the app code doesn't change, only the environment variables do.

import smtplib
from email.message import EmailMessage

from app.core.config import settings

# smtplib defaults to no timeout at all, which means a mail server that
# accepts the TCP connection and then goes quiet blocks *forever*.
# send_email is called synchronously from inside a request handler
# (api/auth.py's password-reset request), so each stalled send holds a
# worker thread indefinitely -- enough of them and the API stops
# responding. Ten seconds is generous for an SMTP handshake.
SMTP_TIMEOUT_SECONDS = 10

SMTP_INSECURE_AUTH_MESSAGE = (
    "SMTP_USERNAME is set but SMTP_USE_TLS is not -- refusing to send SMTP credentials "
    "over an unencrypted connection. Set SMTP_USE_TLS=true, or clear SMTP_USERNAME if "
    "the relay doesn't need authentication."
)


def validate_email_settings() -> None:
    """Fail fast at startup on an SMTP config that would leak credentials.

    Called from main.py's lifespan. Checking here rather than only at send
    time means the misconfiguration surfaces immediately on deploy, in the
    logs, instead of the first time a user happens to request a password
    reset.
    """
    if settings.smtp_username and not settings.smtp_use_tls:
        raise RuntimeError(SMTP_INSECURE_AUTH_MESSAGE)


def send_email(to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
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
            # than a bare RuntimeError so api/auth.py's existing handler
            # catches and logs it. If it escaped as a 500, the reset
            # endpoint would answer 500 for a registered address and 200
            # for an unregistered one -- handing back exactly the account
            # enumeration that its generic response message exists to
            # prevent. validate_email_settings() below is what makes this
            # loud, at startup, where it can't leak anything.
            if not settings.smtp_use_tls:
                raise smtplib.SMTPException(SMTP_INSECURE_AUTH_MESSAGE)
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
