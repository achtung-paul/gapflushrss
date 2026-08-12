# Shared helpers for backup_client.py and restore_client.py. Not a
# script itself -- imported by the two that are. See
# docs/BACKUP_RESTORE.md for the snapshot format this writes/reads and
# why a snapshot isn't just a plain pg_dump.

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core.crypto import decrypt_secret
from app.core.config import settings

# The tables that make up one client's Commodity-and-below data
# (ProjectBase, alembic_project/) -- everything a Project owns. Always
# used to scope a pg_dump to just these, never the whole database --
# two reasons, not just one: (1) when the client's PostgresService is
# the "Default" one that also holds this app's own central tables (see
# CLAUDE.md's "Default service shares the central database" note),
# dumping the whole database would sweep in every other client's users,
# projects, and clients rows too; (2) even on a genuinely dedicated
# database, the database also holds `alembic_version_project` -- schema
# bookkeeping, not client data -- and restoring that row on top of a
# target database's own (already-correct) row is a primary-key conflict
# that pg_restore refuses. Caught by actually running a restore against
# a real deployment, not by code review.
PROJECT_TABLES = [
    "commodities",
    "standard_tolerances",
    "analyses",
    "analysis_entries",
    "chain_components",
    "angled_components",
    "images",
    "markers",
    "analysis_images",
]

# Central-DB tables that belong to one client, in the order they must be
# restored (parents before the children that FK to them). Keyed to the
# JSON key used for each table in central.json.
CENTRAL_TABLES = {
    "process_types": "process_type_id",
    "tolerance_groups": "tolerance_group_id",
    "dimension_ranges": "dimension_range_id",
    "tolerance_values": "tolerance_value_id",
    "users": "user_id",
    "projects": "project_id",
    "groups": "group_id",
    "user_group_project": None,  # composite key, no single id column
}


def snapshot_dir_for(client_row, timestamp: datetime | None = None) -> Path:
    # A readable, filesystem-safe directory name -- the client_id suffix
    # is what actually disambiguates two clients with a similar name, the
    # slugified name is just so a human skimming `ls` doesn't have to
    # cross-reference ids.
    timestamp = timestamp or datetime.now(timezone.utc)
    slug = "".join(c if c.isalnum() else "-" for c in client_row["name"]).strip("-").lower() or "client"
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    return Path(settings.backup_dir) / f"{slug}-{client_row['client_id']}-{stamp}"


def shares_central_database(service_row: dict) -> bool:
    # True only for a PostgresService that points at this app's own
    # central database -- currently just the "Default" service seeded by
    # alembic/versions/fe5a0c40a1ce. Compared on host+port+database, not
    # just name, so it still works correctly if "Default" is ever
    # renamed.
    return (
        service_row["host"] == settings.postgres_host
        and service_row["port"] == settings.postgres_port
        and service_row["database"] == settings.postgres_db
    )


def pg_env(service_row: dict) -> dict:
    # PGPASSWORD is how pg_dump/pg_restore take a password non-interactively
    # -- there's no --password-file flag on these tools. This only ever
    # runs as a short-lived subprocess, so the exposure window is small,
    # but it's still a plaintext password in the child process's
    # environment for that window.
    env = os.environ.copy()
    env["PGPASSWORD"] = decrypt_secret(service_row["encrypted_password"])
    return env


def pg_dump_project_db(service_row: dict, dest_file: Path) -> None:
    command = [
        "pg_dump",
        "-h", service_row["host"],
        "-p", str(service_row["port"]),
        "-U", service_row["username"],
        "-d", service_row["database"],
        "-Fc",  # custom format -- what pg_restore expects, and compressed
        "-f", str(dest_file),
    ]
    for table in PROJECT_TABLES:
        command += ["-t", table]
    subprocess.run(command, env=pg_env(service_row), check=True)


def write_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
