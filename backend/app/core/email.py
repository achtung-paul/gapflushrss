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


def send_email(to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
