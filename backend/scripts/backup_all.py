#!/usr/bin/env python3
"""Nightly backup: a full dump of the central database, plus one
per-client snapshot (scripts/backup_client.py) for every registered
client. Intended for cron on the LXC:

    0 2 * * * docker compose exec -T backend python scripts/backup_all.py

The central dump is a plain whole-database pg_dump -- unlike a client
snapshot, it's never read back by anything client-facing, so there's no
tenancy boundary to preserve here; it's the same kind of backup
CLAUDE.md already recommends before a risky migration, just automated
and dated instead of a one-off manual step.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from scripts.backup_client import main as backup_client


def _dump_central_database() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = f"{settings.backup_dir}/central-{stamp}.dump"
    # settings.postgres_password is the app's own central-DB password,
    # stored in plaintext env vars -- unlike a *registered* service's
    # password (core/crypto.py), it was never encrypted in the first
    # place, so there's nothing to decrypt here.
    subprocess.run(
        [
            "pg_dump",
            "-h", settings.postgres_host,
            "-p", str(settings.postgres_port),
            "-U", settings.postgres_user,
            "-d", settings.postgres_db,
            "-Fc",
            "-f", dest,
        ],
        env={**os.environ, "PGPASSWORD": settings.postgres_password},
        check=True,
    )
    print(f"Central database backed up to {dest}")


def main() -> None:
    _dump_central_database()

    db = SessionLocal()
    try:
        client_ids = [row.client_id for row in db.execute(text("SELECT client_id FROM clients"))]
    finally:
        db.close()

    # One client's backup failing (unreachable service, full disk, ...)
    # must not stop every other client from getting backed up tonight --
    # same reasoning as core/bootstrap.py's upgrade_initialized_services.
    # Exits non-zero at the end if anything failed, so cron still emails
    # a failure notice even though the run as a whole "succeeded".
    failures = []
    for client_id in client_ids:
        print(f"Backing up client {client_id}...")
        try:
            backup_client(client_id)
        except Exception as error:
            print(f"Backup FAILED for client {client_id}: {error}", file=sys.stderr)
            failures.append(client_id)

    if failures:
        print(f"{len(failures)} client backup(s) failed: {failures}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
