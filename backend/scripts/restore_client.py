#!/usr/bin/env python3
"""Restore one client from a snapshot written by scripts/backup_client.py.

Usage (from the LXC):
    docker compose exec backend python scripts/restore_client.py <snapshot_dir>

<snapshot_dir> is the path *inside the container* (matches settings.backup_dir,
mounted as the `backups` volume -- see docker-compose.yml), e.g.:
    docker compose exec backend python scripts/restore_client.py \\
        /var/backups/stackfitpro/acme-7-20260811T020000Z

Requirements, checked before anything is written:
  - No client currently has this snapshot's client_id (the usual case
    after DELETE /admin/clients/{id}'s purge -- see api/admin_clients.py
    -- which removes the client's row along with everything else).
  - The PostgresService and MinioService ids recorded in the snapshot
    still exist and are reachable. This script does not recreate a
    deleted service -- if the physical infrastructure itself was torn
    down, register a replacement service first and see
    docs/BACKUP_RESTORE.md for restoring onto a *different* service id.

Central rows are re-inserted with their original ids, not fresh
auto-generated ones -- required because ChainComponent.tolerance_value_id
and Commodity.project_id are plain integers into the central database,
not real foreign keys (no FK is possible across the database boundary --
see CLAUDE.md), so anything that changed those ids would silently orphan
every commodity, analysis, chain component and image under this client.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text

from app.core.crypto import decrypt_secret
from app.db.session import SessionLocal
from scripts._snapshot import CENTRAL_TABLES, pg_env

# Insertion order matters: each table here must come after every table
# it has a foreign key into. user_group_project is last because it
# references three of the others.
INSERT_ORDER = [
    "users",
    "projects",
    "groups",
    "process_types",
    "tolerance_groups",
    "dimension_ranges",
    "tolerance_values",
    "user_group_project",
]


def _read_json(path: Path):
    import json

    with open(path) as f:
        return json.load(f)


def _insert_rows(db, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    column_list = ", ".join(columns)
    db.execute(text(f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"), rows)

    # Bring the table's auto-increment sequence up past the id we just
    # inserted by hand -- otherwise the next ordinary INSERT (via the
    # app, not this script) collides with a restored row. Tables with a
    # composite key (user_group_project) have no single sequence to fix.
    id_column = CENTRAL_TABLES.get(table)
    if id_column is not None:
        db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{id_column}'), "
                f"(SELECT COALESCE(MAX({id_column}), 1) FROM {table}))"
            )
        )


def main(snapshot_dir: Path) -> None:
    """Restore, in an order chosen so a failure never leaves a half-restored client.

    pg_restore and the MinIO upload run *before* anything is written to
    the central database -- both are external processes/services this
    script can't wrap in a database transaction, so the only way to keep
    a failure there from being visible is to not touch the central DB
    until they've already succeeded. An earlier version inserted the
    central rows (including the `clients` row itself) first and only
    then ran pg_restore -- when pg_restore failed, the already-committed
    `clients` row was left behind: deactivated, with no project data
    behind it, and blocking its Postgres/MinIO services from being
    reused by a new client. Caught by deliberately failing a restore
    (a version-mismatched pg_dump/pg_restore) against a real deployment,
    not by code review. Now: nothing is visible in the central database
    at all until every other step has already succeeded, and if this
    script is re-run after such a failure, there is nothing to clean up
    first.
    """
    manifest = _read_json(snapshot_dir / "manifest.json")
    central = _read_json(snapshot_dir / "central.json")
    client_id = manifest["client_id"]

    print(f"Restoring client {client_id!r} ({manifest['client_name']!r}) from {snapshot_dir}")

    db = SessionLocal()
    try:
        existing = db.execute(
            text("SELECT 1 FROM clients WHERE client_id = :cid"), {"cid": client_id}
        ).first()
        if existing is not None:
            print(
                f"A client with id {client_id} already exists -- refusing to restore over it. "
                "See docs/BACKUP_RESTORE.md.",
                file=sys.stderr,
            )
            sys.exit(1)

        postgres_service = db.execute(
            text("SELECT * FROM postgres_services WHERE postgres_service_id = :sid"),
            {"sid": manifest["postgres_service_id"]},
        ).mappings().first()
        minio_service = db.execute(
            text("SELECT * FROM minio_services WHERE minio_service_id = :sid"),
            {"sid": manifest["minio_service_id"]},
        ).mappings().first()
        if postgres_service is None or minio_service is None:
            print(
                "The Postgres/MinIO service this snapshot was taken from no longer exists -- "
                "register a replacement first. See docs/BACKUP_RESTORE.md.",
                file=sys.stderr,
            )
            sys.exit(1)
        postgres_service = dict(postgres_service)
        minio_service = dict(minio_service)

        # 1. The project database -- data only, since the tables already
        # exist (this project's Postgres service was never torn down by
        # a purge, only its rows were -- see api/admin_clients.py's
        # DELETE /admin/clients/{id}). --disable-triggers lets rows land
        # out of FK order during a data-only restore without Postgres
        # rejecting them mid-way.
        subprocess.run(
            [
                "pg_restore",
                "--data-only",
                "--disable-triggers",
                "-h", postgres_service["host"],
                "-p", str(postgres_service["port"]),
                "-U", postgres_service["username"],
                "-d", postgres_service["database"],
                str(snapshot_dir / "project_db.dump"),
            ],
            env=pg_env(postgres_service),
            check=True,
        )
        print("Project database restored.")

        # 2. MinIO objects.
        from minio import Minio

        minio_client = Minio(
            minio_service["endpoint"],
            access_key=minio_service["access_key"],
            secret_key=decrypt_secret(minio_service["encrypted_secret_key"]),
            secure=minio_service["secure"],
        )
        objects_dir = snapshot_dir / "objects"
        restored = 0
        for file_path in objects_dir.rglob("*"):
            if file_path.is_file():
                object_key = str(file_path.relative_to(objects_dir))
                minio_client.fput_object(minio_service["bucket"], object_key, str(file_path))
                restored += 1
        print(f"{restored} MinIO object(s) restored.")

        # 3. Only now does anything become visible in the central
        # database -- the clients row itself, restored deactivated
        # regardless of what the snapshot recorded (a purge always
        # deactivates first -- see api/admin_clients.py), then every
        # other central row in dependency order with its original id,
        # then reactivation, all committed together as the last step.
        client_row = dict(central["client"])
        client_row["is_active"] = False
        columns = ", ".join(client_row.keys())
        placeholders = ", ".join(f":{c}" for c in client_row)
        db.execute(text(f"INSERT INTO clients ({columns}) VALUES ({placeholders})"), client_row)
        db.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('clients', 'client_id'), "
                "(SELECT COALESCE(MAX(client_id), 1) FROM clients))"
            )
        )
        for table in INSERT_ORDER:
            _insert_rows(db, table, central.get(table, []))
        db.execute(text("UPDATE clients SET is_active = true WHERE client_id = :cid"), {"cid": client_id})
        db.commit()
        print(f"Client {client_id} restored and reactivated. Restore complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/restore_client.py <snapshot_dir>", file=sys.stderr)
        sys.exit(1)
    main(Path(sys.argv[1]))
