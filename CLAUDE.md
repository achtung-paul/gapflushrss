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

frontend/src/
  pages/       route-level components
  components/  shared/reusable pieces (annotator, charts, chain section)
  api/client.js  single fetch wrapper + one exported function per endpoint
  auth/        AuthContext + ProtectedRoute
```

### Central DB vs. per-project services

Users, Projects (the registry), Groups/memberships, admin config, Postgres/MinIO
service definitions, and the Process Type/tolerance matrix all live in the
app's one fixed central database (`db/session.py`, `alembic/`). `Commodity`
and everything under it (`Analysis`, `AnalysisEntry`, `ChainComponent`,
`Marker`, `Image`, `AnalysisImage`) live on whichever Postgres service that
row's `Project` is assigned to (`db/project_base.py`, `alembic_project/`,
`core/service_db.py`) — different projects can be on different physical
services. Every API route for Commodity-and-below is nested under
`/projects/{project_id}/...` specifically so the backend knows which
database to open *before* touching any data (see `api/deps.py`'s
`get_project_db`) — there's no other way to resolve it, since a bare
`analysis_id`/`marker_id`/etc. doesn't say which service it lives on.

## Critical gotchas (read before touching related code)

- **Groups have no FK to Project.** A project's three groups (`Project-<Name>-Managers/Contributors/Viewers`) are found only by reconstructing that name string (`_group_name` in `api/projects.py`, `user_can_manage_project` in `api/deps.py`). Renaming a project **must** rename its three groups or members silently lose access; deleting a project **must** explicitly delete its groups since nothing cascades them.
- **MinIO never cascades at the DB level.** Deleting an `Image`/`AnalysisImage` row does not delete the underlying object — call `service_storage.delete_image(minio_service, object_key)` *before* the DB row disappears, since `object_key` is the only record of where the file lives.
- **`Commodity.project_id` and `ChainComponent.tolerance_value_id` are plain columns, not real foreign keys** — Postgres can't enforce a FK across two separate databases, and `Commodity` (project-scoped) references `Project` (central) / `ChainComponent` references `ToleranceValue` (central) across exactly that boundary. Two consequences: (1) nothing stops a stray `project_id` value from pointing at a different, colocated project's rows if two projects share a physical Postgres service — every fetch of Commodity-and-below data must explicitly check ownership (`project_id == expected`), not just existence; see `_get_commodity_or_404` and everything chained off it in `api/analyses.py`. (2) deleting a `Project` doesn't cascade to its `Commodity` rows the way it used to — `api/projects.py`'s `delete_project` deletes them by hand.
- **Destructive UI actions require a confirm pop-up**, not `window.confirm()` (native dialogs block browser automation and are jarring in-app). Standing pattern: inline `pendingDeleteId` / `confirmingRenameId` state per row showing "Action? [Yes] [No]" — see `ProjectListPage.jsx` or `ProcessTypesPage.jsx` for the reference implementation.
- **Annotorious v2 has no default export** — `import { init } from '@recogito/annotorious'`, not a default import. `disableEditor: true` alone silently discards drawn shapes on deselect unless `allowEmpty: true` is also set (`saveSelected()` checks `bodies.length > 0 || config.allowEmpty` internally).
- **`useCallback` dependency arrays must match captured variables exactly.** An incomplete array (especially `[]`) permanently captures an early-render closure — this caused markers to silently no-op on delete. Don't mask the eslint `exhaustive-deps` warning with a disable comment; fix the array instead.
- **Alembic autogenerate can misorder drops when a whole table is being removed** — if a migration drops a table that something still has an FK to, drop the dependent FK/column first. Simple `ondelete` alterations on existing FKs (not table drops) autogenerate correctly and don't need this fix.
- **Two separate Alembic chains exist** (see Migrations below) — mixing up which one a change belongs to (central model vs. a `ProjectBase` model) will autogenerate against the wrong metadata.

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

## Deploying to the test LXC

The LXC's `/opt/gapflushrss` (`192.168.4.78`, root, key at `~/.ssh/proxmox_test_server_private.pem`) is a **plain file copy, not a git checkout** — commits here don't appear there automatically.
```
scp -i ~/.ssh/proxmox_test_server_private.pem <local_path> root@192.168.4.78:/opt/gapflushrss/<same_relative_path>
ssh -i ~/.ssh/proxmox_test_server_private.pem root@192.168.4.78 "cd /opt/gapflushrss && docker compose build <service> && docker compose up -d <service>"
```
For a change touching many files (e.g. a whole feature), `rsync -avz --exclude='__pycache__' --exclude='*.pyc' -e "ssh -i ~/.ssh/proxmox_test_server_private.pem" <local_dir>/ root@192.168.4.78:/opt/gapflushrss/<same_dir>/` is faster than scp-ing one file at a time and keeps the same "only copy what changed" property.

Frontend runs the Vite dev server inside its container (not a static build) with no bind-mounted volume, so even frontend-only edits need the full build+up cycle to show up.

## Reference material that can't be committed

If the user shares proprietary reference material (e.g. a standard's table) for context, use it to inform the data model but don't commit the image/file itself — keep it out of the working tree entirely (chat-shared only).
