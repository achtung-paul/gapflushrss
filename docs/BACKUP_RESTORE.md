# Backup and restore

Per-client backup/restore is host scripts plus this runbook, not an app feature.
That's deliberate: root admin cannot see any client's data through the product
(see `PROJECT_BRIEF.md`'s RBAC section and `CLAUDE.md`'s tenancy-boundary
gotcha), and an app route that reads a client's whole dataset out to a backup
file would partly reopen that boundary. The one exception is the snapshot
`DELETE /admin/clients/{id}` takes automatically before it purges a client
(`api/admin_clients.py`'s `delete_client`) -- that one writes to disk and never
returns data to the caller, so it doesn't have the same problem.

Everything below runs **inside the backend container**, where
`core/crypto.py`'s `SERVICE_CREDENTIAL_KEY` and the central database
connection are both available -- these scripts need live credentials for a
specific client's registered services, not just the app's own schema, so they
can't run standalone the way a plain Python one-off sometimes can.

## What one client's snapshot contains

Dedicated infrastructure per client (see `models/client.py`) makes this clean:
a client's data is exactly its own Postgres database, its own MinIO bucket,
and a scoped set of central-DB rows. `scripts/backup_client.py` writes one
timestamped directory per client under `BACKUP_DIR`
(`/var/backups/stackfitpro` by default -- the `backups` volume in
`docker-compose.yml`):

| File | Contents |
|---|---|
| `manifest.json` | Client id/name, which services it's on, row/object counts -- read this first |
| `central.json` | Every central-DB row this client owns (`clients`, `users`, `projects`, `groups`, `user_group_project`, `process_types`, `tolerance_groups`, `dimension_ranges`, `tolerance_values`), **with original primary keys** |
| `project_db.dump` | `pg_dump -Fc` of the client's Postgres database (or, for the legacy "Default" client only, just the Commodity-and-below tables -- see below) |
| `objects/` | Every object in the client's MinIO bucket |

### Why central rows keep their original ids

`Commodity.project_id` (and `ChainComponent.tolerance_value_id`) are plain
integers into the central database, not real foreign keys -- Postgres can't
enforce a FK across two separate databases (see `CLAUDE.md`). A restore that
let Postgres assign fresh ids to `projects`/`users`/etc. would silently orphan
every commodity, analysis, chain component and image under that client: the
project data would still say `project_id = 7`, but the restored project might
now be id 41. `scripts/restore_client.py` inserts every central row with its
original id and then advances that table's sequence past it, specifically to
avoid this.

### The "Default Client" special case

One deployment quirk, inherited from before this feature existed: the
"Default" `PostgresService` (seeded by
`alembic/versions/fe5a0c40a1ce_multi_service_postgres_minio.py`) points at
`settings.postgres_db` -- **the same database that holds this app's own
central tables**. A plain whole-database `pg_dump` of that service would
therefore capture every other client's central rows too, not just the Default
client's project data.

`scripts/_snapshot.py`'s `shares_central_database()` detects this (by
comparing host/port/database against the app's own central connection) and,
when true, `pg_dump` is scoped to just the Commodity-and-below tables via
`-t` flags instead of dumping the whole database. `manifest.json` records
`shares_central_database: true` when this happened, so a human reviewing a
snapshot can tell at a glance.

This only ever applies to the Default client. Every client created going
forward gets a genuinely dedicated Postgres service (`api/admin_clients.py`'s
`create_client` refuses to assign an already-assigned service), so this
branch should become dead code once the Default client is migrated onto its
own database -- see the follow-up note in `CLAUDE.md`.

## Manual backup

```
docker compose exec backend python scripts/backup_client.py <client_id>
```

Finds the client id from `GET /admin/clients` (root admin's Clients screen)
or `SELECT client_id, name FROM clients;` against the central database.

## Scheduled backup

```
docker compose exec backend python scripts/backup_all.py
```

Dumps the whole central database (a plain `pg_dump`, since it's never read
back by anything client-facing -- there's no tenancy boundary to preserve for
this one), then runs `backup_client.py` for every registered client. One
client's backup failing (unreachable service, full disk, ...) does not stop
the rest -- see the script's own comment. Put this on cron on the LXC:

```
0 2 * * * cd /opt/gapflushrss && docker compose exec -T backend python scripts/backup_all.py >> /var/log/gapflushrss-backup.log 2>&1
```

**The `backups` volume needs the same access control as the database itself**
-- a snapshot is a full tenant's data, unencrypted, on disk. This belongs on
`CLAUDE.md`'s production checklist alongside TLS for Postgres/MinIO.

## Restore

```
docker compose exec backend python scripts/restore_client.py <snapshot_dir>
```

`<snapshot_dir>` is the path *inside the container* (the `backups` volume
mount point), e.g.
`/var/backups/stackfitpro/acme-7-20260811T020000Z`.

**Before running this:**

1. Confirm no client currently has this snapshot's `client_id` -- the normal
   case immediately after a purge (`DELETE /admin/clients/{id}` deletes the
   `clients` row along with everything else). The script refuses to restore
   over an existing client id.
2. Confirm the `PostgresService`/`MinioService` ids recorded in
   `manifest.json` still exist and are reachable (`GET /admin/postgres-services`,
   `GET /admin/minio-services`). This script does **not** recreate a deleted
   service. If the physical infrastructure itself was torn down, register a
   replacement service, restore the project database's schema onto it by hand
   (`docker compose exec backend alembic -c alembic_project.ini upgrade head -x db_url=...`
   -- see `CLAUDE.md`'s Migrations section), then edit `manifest.json`'s
   `postgres_service_id`/`minio_service_id` to point at the replacement before
   running the restore script.

What it does, in order -- deliberately central-database-last, not first (see
below):

1. `pg_restore --data-only --disable-triggers`'s `project_db.dump` into the
   target Postgres service's database. `--data-only` because the tables
   already exist (a purge never drops them -- see `CLAUDE.md`'s MinIO/Group
   gotcha reasoning, same principle); `--disable-triggers` lets rows land out
   of FK order without Postgres rejecting them mid-restore.
2. Re-uploads every file under `objects/` to the target MinIO bucket.
3. Only now does anything touch the central database: re-inserts every row
   from `central.json` with its original id (client, users, projects, groups,
   memberships, process types, and the whole tolerance matrix), advances each
   table's sequence past the highest id it just inserted, reactivates the
   client (`is_active = true`), and commits all of it together as one step.

**Central rows go last, not first.** An earlier version inserted the
`clients` row before running `pg_restore`, on the theory that each step
should only start once the previous one succeeded. In practice this meant a
`pg_restore` failure (caught in testing -- see "pg_dump/pg_restore version
must match the server" below) left an already-committed `clients` row
behind: deactivated, with no project data behind it, and blocking its
Postgres/MinIO services from being reused by a new client, since
`pg_restore`/MinIO aren't things a database transaction can wrap. Central
rows only ever appear now once everything they'd reference already exists,
so a failure at step 1 or 2 leaves nothing in the central database to clean
up before retrying. If an old snapshot ever leaves a deactivated,
projectless `clients` row behind anyway (from a restore run before this
fix), delete that row by hand before retrying the restore.

### pg_dump/pg_restore version must match the server

`backend/Dockerfile` installs `postgresql-client-16` specifically, from the
official PGDG apt repository, not Debian's own default `postgresql-client`
package. Caught the hard way: Debian's default package tracks whatever
major version Debian currently ships (17, on the `python:3.13-slim` base
image's Debian release), and a *newer* `pg_dump` can emit settings an
*older* server doesn't recognise -- specifically `SET transaction_timeout = 0`,
a PostgreSQL 17 addition that our bundled `postgres:16-alpine` server
rejects with "unrecognized configuration parameter", breaking every
`pg_restore`. If `docker-compose.yml`'s `postgres` image version ever
changes, update the Dockerfile's `postgresql-client-<NN>` pin to match, and
re-run a real backup/restore cycle before trusting it -- this class of bug
only shows up when the two are actually exercised together, not from
reading either script.

**Test the restore path for real, into a throwaway client, before trusting
it** -- same reasoning as `CLAUDE.md`'s migration-rehearsal procedure. Back up
a disposable test client, purge it, restore it, and confirm a user can log in
and open an analysis with its images intact. Specifically check that the
*restored* `project_id` values match the originals -- a mismatch there won't
raise an error, it'll show up quietly as an empty commodity list.

## Verifying a restore

After restoring, as the client's own client_admin (not root admin, who still
can't see any of this):

- `GET /projects` lists the same projects as before the purge.
- Open a project's commodities and confirm images render (proves both the
  `project_id` linkage and the MinIO re-upload worked).
- `GET /process-types` shows the client's tolerance matrix, including any
  tolerance values.
- A `GET /client-admin/users` list matches what the client had before.
