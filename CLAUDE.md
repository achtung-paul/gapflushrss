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
  core/       config, security, storage (MinIO), email, simulation math
  db/         session, declarative base
  alembic/versions/   migrations

frontend/src/
  pages/       route-level components
  components/  shared/reusable pieces (annotator, charts, chain section)
  api/client.js  single fetch wrapper + one exported function per endpoint
  auth/        AuthContext + ProtectedRoute
```

## Critical gotchas (read before touching related code)

- **Groups have no FK to Project.** A project's three groups (`Project-<Name>-Managers/Contributors/Viewers`) are found only by reconstructing that name string (`_group_name` in `api/projects.py`, `user_can_manage_project` in `api/deps.py`). Renaming a project **must** rename its three groups or members silently lose access; deleting a project **must** explicitly delete its groups since nothing cascades them.
- **MinIO never cascades at the DB level.** Deleting an `Image` row does not delete the underlying object — call `delete_image(object_key)` (`core/storage.py`) *before* the DB row disappears, since `object_key` is the only record of where the file lives.
- **Destructive UI actions require a confirm pop-up**, not `window.confirm()` (native dialogs block browser automation and are jarring in-app). Standing pattern: inline `pendingDeleteId` / `confirmingRenameId` state per row showing "Action? [Yes] [No]" — see `ProjectListPage.jsx` or `ProcessTypesPage.jsx` for the reference implementation.
- **Annotorious v2 has no default export** — `import { init } from '@recogito/annotorious'`, not a default import. `disableEditor: true` alone silently discards drawn shapes on deselect unless `allowEmpty: true` is also set (`saveSelected()` checks `bodies.length > 0 || config.allowEmpty` internally).
- **`useCallback` dependency arrays must match captured variables exactly.** An incomplete array (especially `[]`) permanently captures an early-render closure — this caused markers to silently no-op on delete. Don't mask the eslint `exhaustive-deps` warning with a disable comment; fix the array instead.
- **Alembic autogenerate can misorder drops when a whole table is being removed** — if a migration drops a table that something still has an FK to, drop the dependent FK/column first. Simple `ondelete` alterations on existing FKs (not table drops) autogenerate correctly and don't need this fix.

## Migrations

Generated inside the running backend container (LXC), not locally, then pulled into the repo:
```
docker compose exec backend alembic revision --autogenerate -m "..."
docker cp gapflushrss-backend-1:/app/alembic/versions/<file>.py backend/alembic/versions/<file>.py
```
Inspect the generated file before deploying — check ordering per the gotcha above. `alembic upgrade head` runs automatically on container start (in the Dockerfile's CMD), so a rebuild+restart applies it.

## Deploying to the test LXC

The LXC's `/opt/gapflushrss` (`192.168.4.78`, root, key at `~/.ssh/proxmox_test_server_private.pem`) is a **plain file copy, not a git checkout** — commits here don't appear there automatically.
```
scp -i ~/.ssh/proxmox_test_server_private.pem <local_path> root@192.168.4.78:/opt/gapflushrss/<same_relative_path>
ssh -i ~/.ssh/proxmox_test_server_private.pem root@192.168.4.78 "cd /opt/gapflushrss && docker compose build <service> && docker compose up -d <service>"
```
Frontend runs the Vite dev server inside its container (not a static build) with no bind-mounted volume, so even frontend-only edits need the full build+up cycle to show up.

## Reference material that can't be committed

If the user shares proprietary reference material (e.g. a standard's table) for context, use it to inform the data model but don't commit the image/file itself — keep it out of the working tree entirely (chat-shared only).
