# Sets up where this app's log records actually go, and makes sure no
# secrets end up in them.
#
# Before this existed the app had no logging configuration at all: a
# handful of logger calls, no handlers, no levels, and unhandled
# exceptions going to uvicorn's stdout where nothing could read them back.
# Docker's stdout capture is also lost every time a container is
# recreated, which is every deploy -- so anything worth reviewing later
# has to be written to a file on a volume that survives.
#
# Records are written as JSON Lines (one JSON object per line) rather than
# formatted text because api/logs.py has to parse them back out to serve
# the admin log viewer. Parsing free-form text would mean brittle regex
# against a format nobody remembers choosing.

import json
import logging
import logging.handlers
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

# How many days of logs to keep. The rotating handlers below prune their
# own backups to match, and cleanup_old_logs() sweeps anything they no
# longer own.
LOG_RETENTION_DAYS = 7

# Named so api/logs.py can find the same files without hardcoding paths
# in two places.
BACKEND_LOG_FILENAME = "backend.jsonl"
MINIO_LOG_FILENAME = "minio.jsonl"

# Logger that MinIO webhook entries are written through (see
# api/internal_logs.py). Kept separate from the app's own logger so its
# records land in their own file and can't feed back into the handler
# that produced them.
MINIO_LOGGER_NAME = "stackfitpro.minio"

REDACTED = "[REDACTED]"

# Patterns whose *matched group* is replaced with [REDACTED]. These are
# the values this codebase is actually capable of leaking into a log:
#
# - Connection URLs. core/service_db.py builds Postgres URLs with the
#   password embedded, and SQLAlchemy includes the URL in some connection
#   errors -- so a failed connection can otherwise write a working
#   password straight to disk.
# - The Fernet key, which decrypts every stored service credential.
# - Session and password-reset tokens, which are directly usable to
#   impersonate someone.
# - Authorization headers, which appear in tracebacks of failed outbound
#   calls.
_REDACTION_PATTERNS = [
    # postgresql://user:PASSWORD@host  /  redis://... etc.
    re.compile(r"(?<=://)([^:/@\s]+):([^@/\s]+)(?=@)"),
    # password=... / secret_key=... / token=... in query strings or reprs
    re.compile(r"((?:password|passwd|secret[_-]?key|auth[_-]?token|api[_-]?key)\s*[=:]\s*)([^\s,;&'\")}]+)", re.IGNORECASE),
    # Authorization: Bearer xyz  /  Authorization: rawtoken  /  bearer xyz
    #
    # The "(?:bearer\s+)?" is load-bearing: without it the captured group
    # is the scheme word "Bearer" and the token after it survives
    # untouched, which is the exact opposite of the intent. Caught by
    # testing the pattern against a real header rather than eyeballing it.
    re.compile(r"((?:authorization|bearer)\s*[:=]?\s*(?:bearer\s+)?)(\S+)", re.IGNORECASE),
]


def _redact(text: str) -> str:
    if not text:
        return text

    # The URL pattern has two groups (user, password) and only the second
    # should be masked, so it's handled separately from the rest.
    text = _REDACTION_PATTERNS[0].sub(lambda m: f"{m.group(1)}:{REDACTED}", text)
    for pattern in _REDACTION_PATTERNS[1:]:
        text = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", text)

    # Belt and braces: the Fernet key is a single fixed value, so mask it
    # literally wherever it appears, in case it reaches a log through some
    # shape the patterns above don't match.
    key = settings.service_credential_key
    if key and key in text:
        text = text.replace(key, REDACTED)
    return text


class SecretRedactingFilter(logging.Filter):
    """Scrubs secrets out of a record before any handler formats it.

    Attached to handlers rather than loggers so it applies to everything
    written, including records from third-party libraries (SQLAlchemy,
    urllib3) that this app never calls a logger for directly.

    Redacting here -- on write -- rather than when serving the log viewer
    means the secret never reaches disk at all, so it also can't leak via
    a volume backup or someone reading the file directly.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # getMessage() applies the %-args, so this catches secrets passed
        # as arguments as well as ones already in the format string. The
        # result is stashed back as a plain msg with args cleared, so the
        # formatter doesn't re-expand the unredacted originals.
        try:
            record.msg = _redact(record.getMessage())
            record.args = ()
        except Exception:
            # A record we can't format is not worth losing the whole log
            # over -- leave it for the formatter to deal with.
            pass

        if record.exc_text:
            record.exc_text = _redact(record.exc_text)
        return True


class JsonLinesFormatter(logging.Formatter):
    """One JSON object per line, matching what api/logs.py expects."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            # Timezone-aware and ISO-8601 so entries from all three
            # services sort against each other correctly in the viewer.
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            # formatException output has already been redacted by the
            # filter above when exc_text was set; format it here if not.
            entry["traceback"] = _redact(self.formatException(record.exc_info))
        return json.dumps(entry, default=str)


def _build_file_handler(path: Path, level: int) -> logging.Handler:
    handler = logging.handlers.TimedRotatingFileHandler(
        path,
        when="midnight",
        backupCount=LOG_RETENTION_DAYS,
        utc=True,
        delay=True,  # don't create the file until something is actually logged
    )
    handler.setFormatter(JsonLinesFormatter())
    handler.addFilter(SecretRedactingFilter())
    handler.setLevel(level)
    return handler


def configure_logging() -> None:
    """Attach handlers to the root logger. Call once, before anything logs.

    Safe to call twice (the reloader can re-run startup): existing
    handlers added by this function are removed first, so records don't
    get written two or three times over.
    """
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Drop any handlers a previous call added, identified by the marker
    # attribute set below.
    for existing in list(root.handlers):
        if getattr(existing, "_stackfitpro_handler", False):
            root.removeHandler(existing)
            existing.close()

    file_handler = _build_file_handler(log_dir / BACKEND_LOG_FILENAME, logging.INFO)
    file_handler._stackfitpro_handler = True
    root.addHandler(file_handler)

    # Keep writing to stdout as well, so `docker compose logs backend`
    # still works and startup problems are visible before anyone can
    # reach the admin viewer.
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    console.addFilter(SecretRedactingFilter())
    console._stackfitpro_handler = True
    root.addHandler(console)

    # MinIO's forwarded entries go to their own file. propagate=False
    # stops them also landing in backend.jsonl -- and, more importantly,
    # stops a failure while handling a webhook from being logged back
    # into the stream that MinIO is shipping, which would loop.
    minio_logger = logging.getLogger(MINIO_LOGGER_NAME)
    minio_logger.setLevel(logging.INFO)
    minio_logger.propagate = False
    for existing in list(minio_logger.handlers):
        minio_logger.removeHandler(existing)
        existing.close()
    minio_handler = _build_file_handler(log_dir / MINIO_LOG_FILENAME, logging.INFO)
    minio_handler._stackfitpro_handler = True
    minio_logger.addHandler(minio_handler)


def cleanup_old_logs() -> int:
    """Delete log files in LOG_DIR older than LOG_RETENTION_DAYS.

    The rotating handlers already prune the backups they own, so this
    mostly catches files nothing owns any more -- a renamed log, or
    minio.jsonl once that integration is switched off. Returns how many
    files were removed, for the startup log line.

    Only touches LOG_DIR. Postgres writes its CSVs to its own data
    directory (mounted read-only here) and caps itself at seven files via
    a day-of-week filename, so there's nothing for this to do there.
    """
    log_dir = Path(settings.log_dir)
    if not log_dir.is_dir():
        return 0

    cutoff = time.time() - timedelta(days=LOG_RETENTION_DAYS).total_seconds()
    removed = 0
    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError:
            # A file vanishing under us (or being held open) isn't worth
            # failing startup for.
            logging.getLogger(__name__).warning("Could not remove old log file %s", entry.name)
    return removed
