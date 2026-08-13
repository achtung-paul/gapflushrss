# GapFlushRSS

Dimensional Variation Analysis (tolerance stack-up) tool for automotive dimensional engineers. Full spec/scope/data model lives in `PROJECT_BRIEF.md` — read that first for *what* the app does. This file covers *how* to work in the repo.

## Stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL.
- **Frontend:** React (Vite), no chart/UI component libraries by design — hand-rolled SVG/CSS.
- **Storage:** MinIO (S3-compatible) for uploaded images.
- **Proxy:** Nginx, routes `/api/*` to backend, everything else to the Vite dev server.
- **Everything runs via `docker-compose.yml`** inside an LXC on Proxmox. Services: `postgres`, `mailhog`, `minio`, `backend`, `frontend`, `nginx`.

## Code style — non-negotiable

Backend code must stay simple and well-commented, readable by a programmer with ~6 months of experience. This is an explicit constraint from the project brief, not a suggestion. Comments should explain *why*, not *what* — especially non-obvious invariants (see gotchas below, most of which exist because a past silent failure came from skipping this).

## Structure

```
backend/app/
  models/     one file per SQLAlchemy model
  schemas/    Pydantic request/response schemas
  api/        FastAPI routers, one file per resource
  core/       config, security, email, simulation math,
              service_db.py / service_storage.py (per-service Postgres/MinIO
              connections), crypto.py (encrypts stored service credentials)
  db/         session, declarative base (central) + project_base.py
              (Commodity-and-below's separate declarative base)
  alembic/versions/           central-DB migrations
  alembic_project/versions/   project-scoped-DB migrations (own chain)
backend/scripts/  host-run backup/restore (scripts/backup_client.py,
                   backup_all.py, restore_client.py) -- see docs/BACKUP_RESTORE.md

frontend/src/
  pages/       route-level components
  components/  shared/reusable pieces (annotator, charts, chain section)
  api/client.js  single fetch wrapper + one exported function per endpoint
  auth/        AuthContext + ProtectedRoute
```

### Client → Project → Commodity → Analysis

The app is multi-tenant: a `Client` (`models/client.py`) is one SaaS tenant's
sandbox, holding its own users, projects, and reference data (the Process
Type/tolerance matrix), invisible to every other client **and to root_admin**.
`root_admin` is an infrastructure operator, not a superuser — it registers
Postgres/MinIO services and clients, and can never read a client's projects,
users, or tolerance matrix (`User.client_id` is `NULL` for a root_admin; see
the gotcha below). A `client_admin` implicitly has Manager rights on every
project in their own client. See `PROJECT_BRIEF.md`'s RBAC section for the
brief's original two-tier model — this is that plus the Client layer on top.

Isolation is by dedicated infrastructure: root admin assigns each Client
exactly one Postgres service and one MinIO service, and a service is never
assigned to more than one client (`api/admin_clients.py`'s `create_client`).
Projects inherit both from their Client at creation.

### Central DB vs. per-project services

Users, Clients, Projects (the registry), Groups/memberships, admin config,
Postgres/MinIO service definitions, and the Process Type/tolerance matrix all
live in the app's one fixed central database (`db/session.py`, `alembic/`).
`Commodity` and everything under it (`Analysis`, `AnalysisEntry`,
`ChainComponent`, `Marker`, `Image`, `AnalysisImage`) live on whichever
Postgres service that row's `Project` is assigned to (`db/project_base.py`,
`alembic_project/`, `core/service_db.py`) — different projects can be on
different physical services, though every project of one Client is always on
that Client's one assigned service. Every API route for Commodity-and-below
is nested under `/projects/{project_id}/...` specifically so the backend
knows which database to open *before* touching any data (see `api/deps.py`'s
`get_project_db`) — there's no other way to resolve it, since a bare
`analysis_id`/`marker_id`/etc. doesn't say which service it lives on.

## Critical gotchas (read before touching related code)

- **Groups are found by `(project_id, role_name)`, a real FK + column pair, not a name string** (`models/group.py`). This used to be a name like `"Project-<Name>-Managers"`, reconstructed by hand in two places on every lookup — renaming a project had to remember to rewrite all three names or members silently lost access, and deleting a project had to remember to delete its groups since nothing cascaded them. Both problems are gone now: `groups.project_id` has `ondelete="CASCADE"`, so deleting a `Project` takes its Groups (and their `UserGroupProject` rows) with it automatically, and a rename touches no Group row at all. Don't reintroduce a derived-string lookup here.
- **The tenancy boundary lives in exactly three helpers.** `api/deps.py`'s `_user_is_in_project_group` and `user_can_view_project` (both check `user.client_id == project.client_id` before anything else), and `api/reference_data.py`'s `_get_process_type_or_404` (checks `process_type.client_id == current_user.client_id`). Every project-scoped route inherits the first two through `get_project`/`get_project_db`/`get_project_minio_service` — that's what makes root_admin and other clients unable to reach a project's data. A new route that fetches a central-DB row by a client-supplied id **without** going through one of these three (or a helper that itself goes through one) is a cross-tenant read. `api/chain_components.py`'s `_resolve_tolerance_group_name` was exactly this bug — it resolved a client-supplied `tolerance_value_id` with a bare `db.get()` and echoed another client's tolerance group name back in the response; fixed by checking the resolved `ProcessType.client_id` before returning anything.
- **`root_admin` has `User.client_id IS NULL` by design — this is the mechanism, not a gap.** Every tenancy check in `api/deps.py` and `api/reference_data.py` compares `user.client_id` against something; `NULL` matches nothing, which is *how* root_admin ends up with no access to any client's projects, users, or tolerance matrix (per the brief: root admin configures databases/storage and nothing else). Don't "fix" this by giving root_admin a client, and don't add a root_admin short-circuit back into `_user_is_in_project_group`/`user_can_view_project`/`_get_process_type_or_404` the way earlier code had one — that would silently undo the whole tenancy boundary above.
- **Adding a value to a Postgres enum type needs its own transaction, and autogenerate won't do it at all.** `ALTER TYPE ... ADD VALUE` must run inside `op.get_context().autocommit_block()` — Postgres rejects using a new enum value inside the same transaction that added it — and `IF NOT EXISTS` makes a re-run safe. See `alembic/versions/2c3d4e5f6071_client_tenancy.py` (adding `client_admin` to `global_role`). This is a different gotcha from adding an enum *column* to an existing table (below) — enum *values* need the autocommit block; enum *columns* need explicit `CREATE TYPE`.
- **MinIO never cascades at the DB level.** Deleting an `Image`/`AnalysisImage` row does not delete the underlying object — call `service_storage.delete_image(minio_service, object_key)` *before* the DB row disappears, since `object_key` is the only record of where the file lives.
- **`Commodity.project_id` and `ChainComponent.tolerance_value_id` are plain columns, not real foreign keys** — Postgres can't enforce a FK across two separate databases, and `Commodity` (project-scoped) references `Project` (central) / `ChainComponent` references `ToleranceValue` (central) across exactly that boundary. Two consequences: (1) nothing stops a stray `project_id` value from pointing at a different, colocated project's rows if two projects share a physical Postgres service — every fetch of Commodity-and-below data must explicitly check ownership (`project_id == expected`), not just existence; see `_get_commodity_or_404` and everything chained off it in `api/analyses.py`. Every Client now gets a genuinely dedicated Postgres/MinIO service pair (`api/admin_clients.py`'s `create_client` refuses to assign an already-assigned service), so two *different clients'* projects can no longer end up colocated this way — but two projects of the *same* client still can, and the check above is what protects that case. If the one-service-per-client rule is ever relaxed, this plain integer becomes the only thing standing between two tenants' rows. (2) deleting a `Project` doesn't cascade to its `Commodity` rows the way it used to — `api/projects.py`'s `delete_project` (and `api/admin_clients.py`'s `delete_client`, which purges every project of a client) deletes them by hand via `purge_project_data`.
- **Destructive UI actions require a confirm pop-up**, not `window.confirm()` (native dialogs block browser automation and are jarring in-app). Standing pattern: inline `pendingDeleteId` / `confirmingRenameId` state per row showing "Action? [Yes] [No]" — see `ProjectListPage.jsx` or `ProcessTypesPage.jsx` for the reference implementation.
- **Annotorious v2 has no default export** — `import { init } from '@recogito/annotorious'`, not a default import. `disableEditor: true` alone silently discards drawn shapes on deselect unless `allowEmpty: true` is also set (`saveSelected()` checks `bodies.length > 0 || config.allowEmpty` internally).
- **`useCallback` dependency arrays must match captured variables exactly.** An incomplete array (especially `[]`) permanently captures an early-render closure — this caused markers to silently no-op on delete. Don't mask the eslint `exhaustive-deps` warning with a disable comment; fix the array instead.
- **Alembic autogenerate can misorder drops when a whole table is being removed** — if a migration drops a table that something still has an FK to, drop the dependent FK/column first. Simple `ondelete` alterations on existing FKs (not table drops) autogenerate correctly and don't need this fix.
- **Two separate Alembic chains exist** (see Migrations below) — mixing up which one a change belongs to (central model vs. a `ProjectBase` model) will autogenerate against the wrong metadata.
- **`dangerouslySetInnerHTML` is only ever allowed on a value sanitised server-side on write.** There is exactly one such value: `AnalysisEntry.notes`, cleaned by `core/html_sanitize.py`'s `sanitize_notes()` in `api/analyses.py` before it is stored, and rendered in `AnalysisDetailPage.jsx`'s entry view. Sanitising on write (not on render) is what makes the stored value safe for *every* consumer — the API, a future export, anyone reading the table — rather than only the one component that remembered to clean it. Don't render any other field as markup, and don't move the sanitising to the frontend. `ChainComponent.note` is deliberately plain text for the same reason: React escapes it, so it needs no sanitiser and can't become a second XSS sink.
- **Never let `env.py`'s `fileConfig()` run when Alembic is driven from inside the app.** `logging.config.fileConfig()` defaults to `disable_existing_loggers=True` *and* rewrites the root logger's handlers from the `.ini`. Because `core/service_db.py`'s `initialize_schema` runs the project chain programmatically (on startup, and from the admin Initialize button), an unguarded call silently switched off **every** logger the app had already created and detached its file handlers — killing all application logging, and uvicorn's own access logging, for the rest of the process's life, with no error anywhere. Both `env.py` files now wrap the call in `if config.attributes.get("configure_logger", True):`, and `_project_alembic_config()` sets that to `False`. This was invisible for a long time: the only symptom was log lines that "should have appeared" quietly not appearing.
- **`angled_components` is deliberately a separate table from `chain_components`, not shared nullable columns.** An angled-interface row (`direction = Other` on an entry, see `models/angled_component.py`) has an X/Y tolerance pair, not `ChainComponent`'s single ± magnitude, and no Component/Process distinction. Adding nullable `x_tolerance`/`y_tolerance` columns to `chain_components` instead would (1) force a meaningless `contributor_type` value onto every angled row, and (2) make `tolerance_value` nullable, which `api/chain_components.py`'s `get_simulation` reads unguarded (`float(component.tolerance_value)` with no `None` check) — every existing linear read path would need a defensive filter it doesn't have today. Keep the two tables and their math (`core/simulation.py` vs `core/angled_simulation.py`) separate; don't "unify" them later without re-reading this.
- **`require_project_manager` is Manager-only; `require_project_editor` (`api/deps.py`) is Manager-or-Contributor.** Per the brief's Managers/Contributors/Viewers table, Contributors can read/write but not delete — so every *delete* route (and Commodity creation, which the brief reserves for Managers specifically) uses `require_project_manager`; every *create/update* route on Analysis/entries/chain-components/images/markers uses `require_project_editor`. Defaulting a new write route to `require_project_manager` "to be safe" silently locks Contributors out of the ordinary workflow — this happened once already (every write route used it, undetected until a Contributor tried to drop a marker and got a 403).
- **The "Default" `PostgresService` shares its physical database with this app's own central tables.** `fe5a0c40a1ce_multi_service_postgres_minio.py` seeded it from the container's own env vars (`database=settings.postgres_db`) — the single-tenant deployment's original database, adopted as the "Default Client" by `2c3d4e5f6071_client_tenancy.py`. A plain whole-database `pg_dump` of that service therefore captures every other client's central rows too, not just the Default client's project data — `scripts/_snapshot.py`'s `shares_central_database()` detects this and scopes the dump to just the Commodity-and-below tables in that one case. See `docs/BACKUP_RESTORE.md`. Every client created going forward gets a genuinely dedicated service, so this is a one-off legacy case, not a pattern to design around — the fix is migrating the Default Client onto its own database (see the production checklist), not more special-casing.

## Migrations

Two independent chains, since Commodity-and-below can live on a different physical database per project:

- **`alembic/`** — central DB (Users, Projects, Groups, service definitions, tolerance matrix). Runs automatically on every container start (`alembic upgrade head` in the Dockerfile's CMD).
- **`alembic_project/`** — Commodity-and-below's schema. **Not** run automatically — it has no single fixed database. Applied on demand, once per Postgres service, via the admin "Initialize" button (`core/service_db.py`'s `initialize_schema`, which calls `alembic upgrade head` against that one service's connection — idempotent, so it's also how a service gets caught up if this chain grows new migrations later).

Both are generated inside the running backend container (LXC), not locally, then pulled into the repo:
```
docker compose exec backend alembic revision --autogenerate -m "..."
docker cp gapflushrss-backend-1:/app/alembic/versions/<file>.py backend/alembic/versions/<file>.py

# alembic_project has no fixed sqlalchemy.url -- point it at whichever
# service you're generating against (normally the Default one, so
# autogenerate diffs against real, already-adopted tables):
docker compose exec backend alembic -c alembic_project.ini revision --autogenerate -m "..." -x db_url=postgresql+psycopg2://<user>:<pass>@postgres:5432/<db>
docker cp gapflushrss-backend-1:/app/alembic_project/versions/<file>.py backend/alembic_project/versions/<file>.py
```
Inspect the generated file before deploying — check ordering per the gotcha above. A rebuild+restart applies any pending central-chain migration; a project-chain migration additionally needs every already-initialized service caught up via its admin "Initialize" button (or the equivalent call) after deploying.

`alembic/versions/fe5a0c40a1ce_multi_service_postgres_minio.py` is a one-time migration that seeds a "Default" `PostgresService`/`MinioService` from the container's own env vars and backfills every existing Project onto them. It requires `SERVICE_CREDENTIAL_KEY` to be set (see `.env.example`) before it runs — **take a `pg_dump` backup of the LXC's database immediately before deploying it**, not optionally.

It deliberately does **not** touch `commodities`/`analyses`/etc. or the `alembic_project` chain itself — that adoption (recording "already at the project chain's starting revision" without re-running `CREATE TABLE`, plus reshaping `commodities`'s constraints) happens in `core/service_db.py`'s `initialize_schema`, called from `core/bootstrap.py`'s `adopt_default_service_if_needed` on every app startup. **Don't move this logic back inside a migration** — an earlier version tried driving a second Alembic `EnvironmentContext` (`command.stamp`/`command.upgrade` against the `alembic_project` chain) from inside this migration's own `upgrade()`, and the nested context corrupted the outer migration's `op` proxy (`AttributeError: 'NoneType' object has no attribute 'drop_constraint'`), caught by testing against a restored copy of the LXC's DB before it ever touched the real one. Keep migration-triggering-another-migration out of a single call stack.

Within `initialize_schema`, the constraint fixes run **before** `command.stamp`, not after — `command.stamp` commits on its own connection independently of everything else in the function, so if it ran first and the constraint fixes then failed, `check_status` (which only checks whether `alembic_version_project` exists) would report "initialized" on a database that never actually got fixed, with no way to detect or retry it. Same ordering principle applies to any future multi-step "adopt" logic here.

### Testing a risky migration before it touches real data

For any migration that isn't a simple, obviously-reversible column add (like this one — it seeds encrypted credentials and reshapes constraints), rehearse it against a throwaway copy on the *same* Postgres server rather than trusting it on the first real run:
```
docker compose exec postgres pg_dump -U <user> -d <db> -Fc > backup.dump   # keep this regardless
docker compose exec postgres psql -U <user> -d postgres -c "CREATE DATABASE <db>_test OWNER <user>;"
docker compose exec postgres pg_restore -U <user> -d <db>_test < backup.dump
docker compose run --rm -e POSTGRES_DB=<db>_test backend alembic upgrade head
```
`docker compose run --rm -e VAR=value backend <cmd>` overrides an env var for one throwaway container without touching the running `backend` service or its container — safe to use for one-off checks (`alembic upgrade head`, a `python -c "..."` snippet calling app code) against the test copy. Drop the `_test` database when done. This is exactly how the nested-`EnvironmentContext` bug above was caught before it ever ran against the LXC's real data.

## Backup and restore

Per-client backup/restore is host scripts (`backend/scripts/backup_client.py`,
`backup_all.py`, `restore_client.py`) plus a runbook, not an app feature —
root_admin can't see a client's data through the product, and a route that
read a client's whole dataset out to a file would partly reopen that
boundary. Restore is deliberately **not** "run `pg_restore`" — central rows
must be re-inserted with their original ids (`Commodity.project_id` and
`ChainComponent.tolerance_value_id` are plain integers, not real FKs, per the
gotcha above) or every commodity/analysis/chain-component/image under that
client silently orphans. See `docs/BACKUP_RESTORE.md` for the full format,
the Default-Client special case, and the restore procedure.

Two gotchas found only by actually running a backup/restore cycle against a
real deployment, not by reading the scripts (see `docs/BACKUP_RESTORE.md`
for both in full):
- **`pg_dump`/`pg_restore` must be pinned to the server's major version.**
  `backend/Dockerfile` installs `postgresql-client-16` from the official PGDG
  apt repo, not Debian's own default package — Debian tracks whatever major
  version it currently ships (17, as of this writing), and a *newer*
  `pg_dump`'s output can contain settings (`SET transaction_timeout = 0`, a
  PG17 addition) that our `postgres:16-alpine` server rejects, breaking every
  restore with "unrecognized configuration parameter". Update the pin if
  `docker-compose.yml`'s `postgres` image version ever changes.
- **`restore_client.py` writes to the central database last, not first.**
  `pg_restore` and the MinIO upload are external processes a database
  transaction can't wrap — if either fails *after* the `clients` row has
  already been inserted and committed, that row is left behind: deactivated,
  with no project data behind it, and blocking its Postgres/MinIO services
  from ever being reassigned to a new client. Central rows (including
  `clients` itself) are only written once `pg_restore` and the MinIO upload
  have already succeeded, so a failure at either step leaves nothing in the
  central database to clean up before retrying.

## Deploying to the test LXC

The LXC's `/opt/gapflushrss` (`192.168.4.226`, hostname `StackFitPro`, root, key at `~/.ssh/gapfitpro_test_server.pem`) is a **plain file copy, not a git checkout** — commits here don't appear there automatically.
```
scp -i ~/.ssh/gapfitpro_test_server.pem <local_path> root@192.168.4.226:/opt/gapflushrss/<same_relative_path>
ssh -i ~/.ssh/gapfitpro_test_server.pem root@192.168.4.226 "cd /opt/gapflushrss && docker compose build <service> && docker compose up -d <service>"
```
For a change touching many files (e.g. a whole feature), `rsync -avz --exclude='__pycache__' --exclude='*.pyc' -e "ssh -i ~/.ssh/gapfitpro_test_server.pem" <local_dir>/ root@192.168.4.226:/opt/gapflushrss/<same_dir>/` is faster than scp-ing one file at a time and keeps the same "only copy what changed" property.

Frontend runs the Vite dev server inside its container (not a static build) with no bind-mounted volume, so even frontend-only edits need the full build+up cycle to show up. **The backend is the same** — its `uvicorn --reload` makes an `scp` look like it's enough, but there's no bind mount either, so `--reload` only ever watches the code baked into the image. A backend change that appears to have no effect is almost always a missed `docker compose build backend`.

## Production release checklist

Everything below is **deliberately insecure or dev-only in the current test setup** and must change before the app holds real accounts or real data. These are not "nice to have" — each one is a known hole, left open knowingly.

- **Remove Mailhog entirely.** It is a fake SMTP server with **no authentication** that stores every email it receives, including password-reset links, and serves them over an open HTTP API. Anyone who can reach it can request a reset for any known address, read the token, and take over that account — root admin included. Its port is bound to `127.0.0.1` (see `docker-compose.yml`), which stops that from the network but not from anyone with access to the host. Delete the `mailhog` service, point `SMTP_HOST`/`SMTP_PORT` at a real relay, and set `SMTP_USE_TLS=true`. `core/email.py`'s `validate_email_settings()` refuses to start if `SMTP_USERNAME` is set without TLS, so a half-done migration fails loudly at boot rather than leaking mail credentials on every reset.
- **Require TLS on the Postgres connection.** The bundled `postgres` container runs with `ssl=off`, and the app's own central connection (`core/config.py`'s `database_url`) has no `sslmode`, so backend↔database traffic — password hashes, session tokens, encrypted service credentials — is plaintext. `core/service_db.py` already forces `sslmode=require` for *registered* services whose host isn't the bundled one; the central connection and the bundled container both still need doing. Either enable TLS on that container (cert + key, `-c ssl=on`) and add `sslmode=require` to `database_url`, or move the database off-host and require TLS there. Note `sslmode=require` encrypts but does **not** verify the server — use `verify-full` with a CA once certificates are properly managed.
- **Require TLS on the MinIO connection.** `MinioService.secure` defaults to `False` and the bundled MinIO speaks plain HTTP, so uploaded images and the MinIO credentials themselves cross the network unencrypted. Set `secure=True` on every registered MinIO service and terminate TLS properly on the MinIO side. `core/service_storage.py` passes this straight through to the client, so it's a data change plus a MinIO config change, not a code change.
- **Also outstanding:** `cookie_secure=True` once served over HTTPS (`core/config.py`), replacing `uvicorn --reload` with a real production command (`backend/Dockerfile`), and removing the `gapflush`/`gapflush` default credentials in `core/config.py`.
- **Every Client's assigned Postgres/MinIO service must be genuinely dedicated and TLS-enabled.** `api/admin_clients.py`'s `create_client` already refuses to assign a service that's in use by another client, but that's an application-level check, not encryption — see the two TLS items above, which apply per-client-service now, not just to the one bundled `postgres`/`minio` container.
- **Migrate the "Default Client" off the shared database.** It's the one client whose Postgres service is the same physical database as this app's own central tables (see the gotcha above) — a legacy artifact of the pre-multi-tenant deployment, not something new customers get. Create a genuine dedicated database on the same Postgres server, register it as a new service, and move the Default Client onto it (`scripts/backup_client.py` + `scripts/restore_client.py` against the new service, or a manual `pg_dump`/`pg_restore` of just the Commodity-and-below tables) before this deployment holds any other real customer's data on that same server.
- **The `backups` volume needs the same access control as the database itself.** A snapshot (`scripts/backup_client.py`) is a full tenant's data, unencrypted, on disk — anyone who can read `/var/backups/gapflushrss` (the `backups` Docker volume) can read every client's users, projects, and tolerance matrix without going through the app's tenancy checks at all.

## Reference material that can't be committed

If the user shares proprietary reference material (e.g. a standard's table) for context, use it to inform the data model but don't commit the image/file itself — keep it out of the working tree entirely (chat-shared only).
