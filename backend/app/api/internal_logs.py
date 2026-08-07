# Receives MinIO's log events and writes them to this app's log
# directory, so they can be shown alongside backend and Postgres errors in
# the admin log viewer (see api/logs.py).
#
# MinIO has no file logging of its own -- it writes to stdout, which is
# only reachable through the Docker daemon. Rather than give this
# container access to the Docker socket (which is equivalent to root on
# the host), we use MinIO's own webhook logging target: it POSTs each
# batch of events here. See MINIO_LOGGER_WEBHOOK_* in docker-compose.yml.
#
# This endpoint is *not* session-authenticated. MinIO is a service, not a
# browser: it presents a fixed bearer token instead. Three things this has
# to get right, none of them obvious:
#
#  1. It must not log its own failures through the normal logger. MinIO
#     ships whatever the backend logs; if handling a webhook logged an
#     error, that error would be shipped back here, logged again, and
#     loop. Entries go to a dedicated logger with propagate=False, and
#     problems in this handler are answered with a status code rather
#     than a log line.
#  2. It must be exempt from rate limiting. MinIO batches events and
#     core/rate_limit.py keys on X-Real-IP, which isn't set on a direct
#     container-to-container call -- every MinIO event would otherwise
#     share one bucket with anyone else lacking that header.
#  3. With no token configured it must refuse everything, not accept
#     everything. An unauthenticated endpoint that appends to the log
#     store is a log-injection vector: anyone could forge entries and
#     push real ones out of the retention window.

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import settings
from app.core.logging_config import MINIO_LOGGER_NAME

router = APIRouter(prefix="/internal", tags=["internal"])

minio_logger = logging.getLogger(MINIO_LOGGER_NAME)

# MinIO's log entries carry a level of their own; map the ones it sends
# onto Python levels so the viewer's level filter works across services.
_MINIO_LEVELS = {
    "ERROR": logging.ERROR,
    "FATAL": logging.CRITICAL,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
}


def _require_webhook_token(authorization: str | None) -> None:
    expected = settings.minio_log_webhook_token
    if not expected:
        # Not configured -- treat as switched off rather than open.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # MinIO sends the token as the whole Authorization header value, with
    # or without a "Bearer " prefix depending on version, so accept both.
    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _describe(entry: dict) -> tuple[int, str]:
    """Reduce one MinIO log event to (level, message).

    MinIO's shape varies by version and event kind, so this reads
    defensively rather than assuming any particular key is present.
    """
    level_name = str(entry.get("level") or "INFO").upper()
    level = _MINIO_LEVELS.get(level_name, logging.INFO)

    error = entry.get("error") or {}
    message = (
        (error.get("message") if isinstance(error, dict) else None)
        or entry.get("message")
        or entry.get("Message")
        or "MinIO event"
    )

    api = entry.get("api") or {}
    api_name = api.get("name") if isinstance(api, dict) else None
    if api_name:
        message = f"{api_name}: {message}"
    return level, str(message)


@router.post("/minio-logs", status_code=status.HTTP_204_NO_CONTENT)
async def receive_minio_logs(
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_webhook_token(authorization)

    try:
        payload = await request.json()
    except Exception:
        # Deliberately not logged -- see the recursion note at the top.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected JSON")

    # MinIO posts either a single object or a list, depending on batching.
    entries = payload if isinstance(payload, list) else [payload]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        level, message = _describe(entry)
        minio_logger.log(level, message)
