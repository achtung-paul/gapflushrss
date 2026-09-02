#!/usr/bin/env python3
"""Back up one Client's data: its central-DB rows (with original ids), a
pg_dump of its project database, and every object in its MinIO bucket.

Run inside the backend container, where core/crypto.py's
SERVICE_CREDENTIAL_KEY and the central database connection are both
available -- this can't run outside Docker the way a quick one-off
script sometimes can, since it needs live credentials for the specific
client's registered services, not just the app's own schema.

Usage (from the LXC):
    docker compose exec backend python scripts/backup_client.py <client_id>

Writes one timestamped snapshot directory under settings.backup_dir
(BACKUP_DIR, /var/backups/stackfitpro by default -- a Docker volume, see
docker-compose.yml). See docs/BACKUP_RESTORE.md for the full format and
the restore procedure -- notably, why a snapshot is not "just run
pg_restore" and needs its central rows re-inserted with their original
ids.
"""

import sys
from pathlib import Path

sys.path.insert(0, "/app")  # matches PYTHONPATH in the image; needed when run as a plain script

from sqlalchemy import text

from app.core.crypto import decrypt_secret
from app.db.session import SessionLocal
from scripts._snapshot import (
    CENTRAL_TABLES,
    pg_dump_project_db,
    shares_central_database,
    snapshot_dir_for,
    write_json,
)


def _fetch_client_scoped_rows(db, client_id: int) -> dict:
    """Every central-DB row that belongs to this client, keyed by table name.

    Plain SQL rather than the ORM models: this only ever needs to read
    and re-insert whole rows, so there's nothing the ORM's relationship/
    identity-map machinery would add here, and it keeps this script
    decoupled from the app's model classes changing shape later.
    """
    rows: dict[str, list[dict]] = {}

    rows["users"] = [
        dict(r._mapping) for r in db.execute(text("SELECT * FROM users WHERE client_id = :cid"), {"cid": client_id})
    ]
    rows["projects"] = [
        dict(r._mapping)
        for r in db.execute(text("SELECT * FROM projects WHERE client_id = :cid"), {"cid": client_id})
    ]
    project_ids = [p["project_id"] for p in rows["projects"]]

    if project_ids:
        rows["groups"] = [
            dict(r._mapping)
            for r in db.execute(text("SELECT * FROM groups WHERE project_id = ANY(:pids)"), {"pids": project_ids})
        ]
        rows["user_group_project"] = [
            dict(r._mapping)
            for r in db.execute(
                text("SELECT * FROM user_group_project WHERE project_id = ANY(:pids)"), {"pids": project_ids}
            )
        ]
    else:
        rows["groups"] = []
        rows["user_group_project"] = []

    rows["process_types"] = [
        dict(r._mapping)
        for r in db.execute(text("SELECT * FROM process_types WHERE client_id = :cid"), {"cid": client_id})
    ]
    process_type_ids = [p["process_type_id"] for p in rows["process_types"]]

    if process_type_ids:
        rows["tolerance_groups"] = [
            dict(r._mapping)
            for r in db.execute(
                text("SELECT * FROM tolerance_groups WHERE process_type_id = ANY(:ptids)"),
                {"ptids": process_type_ids},
            )
        ]
        rows["dimension_ranges"] = [
            dict(r._mapping)
            for r in db.execute(
                text("SELECT * FROM dimension_ranges WHERE process_type_id = ANY(:ptids)"),
                {"ptids": process_type_ids},
            )
        ]
        tolerance_group_ids = [g["tolerance_group_id"] for g in rows["tolerance_groups"]]
        rows["tolerance_values"] = (
            [
                dict(r._mapping)
                for r in db.execute(
                    text("SELECT * FROM tolerance_values WHERE tolerance_group_id = ANY(:tgids)"),
                    {"tgids": tolerance_group_ids},
                )
            ]
            if tolerance_group_ids
            else []
        )
    else:
        rows["tolerance_groups"] = []
        rows["dimension_ranges"] = []
        rows["tolerance_values"] = []

    return rows


def main(client_id: int) -> Path:
    """Write one snapshot for this client and return the directory it wrote to.

    Raises a plain exception on any failure -- never calls sys.exit --
    because api/admin_clients.py's delete_client calls this in-process
    (same interpreter, inside a request handler) before purging a
    client; sys.exit there would kill the whole backend worker, not just
    this operation.
    """
    db = SessionLocal()
    try:
        client_row = db.execute(
            text("SELECT * FROM clients WHERE client_id = :cid"), {"cid": client_id}
        ).mappings().first()
        if client_row is None:
            raise ValueError(f"No client with id {client_id}")
        client_row = dict(client_row)

        postgres_service = dict(
            db.execute(
                text("SELECT * FROM postgres_services WHERE postgres_service_id = :sid"),
                {"sid": client_row["postgres_service_id"]},
            ).mappings().first()
        )
        minio_service = dict(
            db.execute(
                text("SELECT * FROM minio_services WHERE minio_service_id = :sid"),
                {"sid": client_row["minio_service_id"]},
            ).mappings().first()
        )

        snapshot_dir = snapshot_dir_for(client_row)
        snapshot_dir.mkdir(parents=True, exist_ok=False)
        print(f"Writing snapshot to {snapshot_dir}")

        # 1. central.json -- every row this client owns in the app's own
        # database, with its real primary keys, so restore can put them
        # back exactly as they were rather than letting Postgres assign
        # new ones (see docs/BACKUP_RESTORE.md for why that matters).
        central = {"client": client_row, **_fetch_client_scoped_rows(db, client_id)}
        write_json(snapshot_dir / "central.json", central)

        # 2. project_db.dump -- everything under Project (Commodity and
        # below), always scoped to just those tables (see
        # PROJECT_TABLES's comment in _snapshot.py for why this is
        # unconditional, not just for the "Default" service).
        shares_db = shares_central_database(postgres_service)
        pg_dump_project_db(postgres_service, snapshot_dir / "project_db.dump")

        # 3. objects/ -- the client's whole MinIO bucket. Safe to mirror
        # in full (not filtered by object_key) because a bucket is never
        # shared between two clients -- see models/client.py and
        # api/admin_clients.py's create_client, which refuses to assign
        # an already-assigned MinioService to a second client.
        from minio import Minio  # local import: only backup/restore need this, not the whole app

        minio_client = Minio(
            minio_service["endpoint"],
            access_key=minio_service["access_key"],
            secret_key=decrypt_secret(minio_service["encrypted_secret_key"]),
            secure=minio_service["secure"],
        )
        objects_dir = snapshot_dir / "objects"
        objects_dir.mkdir()
        object_count = 0
        for obj in minio_client.list_objects(minio_service["bucket"], recursive=True):
            minio_client.fget_object(minio_service["bucket"], obj.object_name, str(objects_dir / obj.object_name))
            object_count += 1

        # 4. manifest.json -- a human-readable summary, checked by eye
        # before trusting a snapshot and by restore_client.py before it
        # starts (see that script).
        write_json(
            snapshot_dir / "manifest.json",
            {
                "client_id": client_id,
                "client_name": client_row["name"],
                "postgres_service_id": postgres_service["postgres_service_id"],
                "minio_service_id": minio_service["minio_service_id"],
                "shares_central_database": shares_db,
                "row_counts": {table: len(central[table]) for table in CENTRAL_TABLES if table in central},
                "object_count": object_count,
            },
        )
        print(f"Done. {object_count} MinIO object(s), {len(central['projects'])} project(s).")
        return snapshot_dir
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/backup_client.py <client_id>", file=sys.stderr)
        sys.exit(1)
    try:
        main(int(sys.argv[1]))
    except Exception as error:
        print(f"Backup failed: {error}", file=sys.stderr)
        sys.exit(1)
