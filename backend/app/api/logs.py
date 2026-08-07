# Serves the admin log viewer (frontend/src/pages/LogsPage.jsx): recent
# entries from this app, Postgres and MinIO, normalised into one shape and
# merged into a single time-ordered list.
#
# Three different sources, three formats:
#   backend  -- JSON Lines written by core/logging_config.py
#   minio    -- JSON Lines written by api/internal_logs.py from MinIO's webhook
#   postgres -- CSV written by Postgres itself (log_destination=csvlog),
#               read through a read-only mount of its data directory
#
# Everything here reads from the *end* of each file and stops. This
# endpoint is polled every 5 seconds and a busy Postgres log can be large,
# so nothing may read a whole file into memory.

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import require_root_admin
from app.core.config import settings
from app.core.logging_config import BACKEND_LOG_FILENAME, MINIO_LOG_FILENAME
from app.models.user import User

router = APIRouter(prefix="/admin/logs", tags=["admin"])

logger = logging.getLogger(__name__)

ServiceName = Literal["all", "backend", "postgres", "minio"]
LevelFilter = Literal["all", "error", "warning"]

# Hard cap on what one request can return, independent of the `limit`
# parameter -- this is polled continuously, so the ceiling is what bounds
# the work, not the caller's politeness.
MAX_LIMIT = 500

# How much of the tail of each file to read. Comfortably more than
# MAX_LIMIT entries' worth for any realistic line length, while staying
# small enough to read on every poll without thinking about it.
TAIL_BYTES = 512 * 1024

# Postgres CSV column order is fixed by the server version and documented
# in its manual; these are the only three columns this viewer needs.
_PG_TIMESTAMP_COLUMN = 0
_PG_LEVEL_COLUMN = 11
_PG_MESSAGE_COLUMN = 13

# Postgres severities that count as errors/warnings for the level filter.
_PG_ERROR_LEVELS = {"ERROR", "FATAL", "PANIC"}
_PG_WARNING_LEVELS = {"WARNING"}


class LogEntry(BaseModel):
    timestamp: datetime
    service: str
    level: str
    message: str


class LogsOut(BaseModel):
    entries: list[LogEntry]
    # Which sources actually had a readable file. Lets the UI say "MinIO
    # has produced no logs yet" instead of silently showing nothing, which
    # is indistinguishable from "MinIO is fine".
    available_services: list[str]


def _read_tail(path: Path, max_bytes: int = TAIL_BYTES) -> str:
    """Read at most the last max_bytes of a file, as text.

    Returns "" if the file doesn't exist -- that's the normal state before
    anything has been logged, not an error.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            chunk = handle.read()
    except FileNotFoundError:
        return ""
    except OSError:
        logger.warning("Could not read log file %s", path, exc_info=True)
        return ""

    text = chunk.decode("utf-8", errors="replace")
    # Seeking to a byte offset almost certainly lands mid-line; drop the
    # first partial one rather than trying to parse it.
    if size > max_bytes and "\n" in text:
        text = text.split("\n", 1)[1]
    return text


def _parse_jsonl(text: str, service: str) -> list[LogEntry]:
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            message = raw.get("message", "")
            # The traceback is the useful part of an error; append it so
            # the viewer shows it without needing a second request.
            if raw.get("traceback"):
                message = f"{message}\n{raw['traceback']}"
            entries.append(
                LogEntry(
                    timestamp=datetime.fromisoformat(raw["timestamp"]),
                    service=service,
                    level=str(raw.get("level", "INFO")).upper(),
                    message=message,
                )
            )
        except (ValueError, KeyError, TypeError):
            # A truncated or malformed line shouldn't break the whole view.
            continue
    return entries


def _parse_postgres_csv(text: str) -> list[LogEntry]:
    entries = []
    # csv.reader handles Postgres's quoting (messages routinely contain
    # commas, quotes and newlines), which is why csvlog is used rather
    # than trying to split the default stderr format.
    for row in csv.reader(io.StringIO(text)):
        if len(row) <= _PG_MESSAGE_COLUMN:
            continue
        try:
            # e.g. "2026-08-07 21:15:04.123 UTC"
            stamp = row[_PG_TIMESTAMP_COLUMN].rsplit(" ", 1)[0]
            timestamp = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        entries.append(
            LogEntry(
                timestamp=timestamp,
                service="postgres",
                level=row[_PG_LEVEL_COLUMN].upper(),
                message=row[_PG_MESSAGE_COLUMN],
            )
        )
    return entries


def _postgres_log_files() -> list[Path]:
    log_dir = Path(settings.postgres_log_dir)
    if not log_dir.is_dir():
        return []
    # Postgres cycles through seven day-named files; the most recently
    # written one or two are all that can contain recent entries.
    files = sorted(log_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:2]


def _matches_level(level: str, level_filter: LevelFilter) -> bool:
    if level_filter == "all":
        return True
    if level_filter == "error":
        return level in {"ERROR", "CRITICAL"} | _PG_ERROR_LEVELS
    return level in {"WARNING", "ERROR", "CRITICAL"} | _PG_ERROR_LEVELS | _PG_WARNING_LEVELS


@router.get("", response_model=LogsOut)
def read_logs(
    service: ServiceName = "all",
    level: LevelFilter = "error",
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    _: User = Depends(require_root_admin),
):
    log_dir = Path(settings.log_dir)
    entries: list[LogEntry] = []
    available: list[str] = []

    if service in ("all", "backend"):
        text = _read_tail(log_dir / BACKEND_LOG_FILENAME)
        if text:
            available.append("backend")
        entries.extend(_parse_jsonl(text, "backend"))

    if service in ("all", "minio"):
        text = _read_tail(log_dir / MINIO_LOG_FILENAME)
        if text:
            available.append("minio")
        entries.extend(_parse_jsonl(text, "minio"))

    if service in ("all", "postgres"):
        for path in _postgres_log_files():
            text = _read_tail(path)
            if text and "postgres" not in available:
                available.append("postgres")
            entries.extend(_parse_postgres_csv(text))

    entries = [entry for entry in entries if _matches_level(entry.level, level)]
    # Newest first, then truncate -- so `limit` keeps the most recent
    # entries rather than whichever service happened to be read first.
    entries.sort(key=lambda entry: entry.timestamp, reverse=True)
    return LogsOut(entries=entries[:limit], available_services=available)
