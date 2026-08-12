FROM python:3.13.12-slim

WORKDIR /app

# Makes "import app.xyz" work no matter how a command is invoked in this
# image (uvicorn resolves it from the cwd automatically; plain `alembic`
# does not, since it isn't run as `python -m`).
ENV PYTHONPATH=/app

# scripts/backup_client.py and scripts/restore_client.py need a
# pg_dump/pg_restore that can connect to any registered Postgres service
# over the network (not just the bundled container) -- the same libpq
# client works whether the target is "postgres:5432" on this compose
# network or a remote host, since the connection is always by
# host/port/credentials, never a Unix socket.
#
# Pinned to major version 16, matching docker-compose.yml's
# `postgres:16-alpine` -- Debian's own default postgresql-client package
# tracks whatever major version Debian currently ships (17 on trixie),
# and a *newer* pg_dump's output can contain settings an *older* server
# doesn't recognise (e.g. PG17's "SET transaction_timeout = 0"), which
# breaks pg_restore against our PG16 server with an "unrecognized
# configuration parameter" error -- caught by actually running a
# backup/restore against a real deployment before trusting this, not by
# code review. The official PGDG apt repo carries every recent major
# version side by side, unlike Debian's own repo.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /etc/apt/keyrings/postgresql.asc \
    && chmod a+r /etc/apt/keyrings/postgresql.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/etc/apt/keyrings/postgresql.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so Docker can cache this layer when only
# application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY alembic_project ./alembic_project
COPY alembic_project.ini .
COPY scripts ./scripts
# Included so the suite can be run against the real image with
# `docker compose run --rm --no-deps backend python -m pytest tests/`.
# Drop this (and pytest from requirements.txt) when the production image
# is split out in Phase 9.
COPY tests ./tests

EXPOSE 8000

# Apply any pending *central* database migrations, then start the
# server. The alembic_project chain (Commodity and below -- see
# alembic_project/env.py) is deliberately NOT run here: it has no single
# fixed database to upgrade on every boot, since it runs per-service.
# It's applied on demand, once per service, via the admin "Initialize"
# button (core/service_db.py's initialize_schema()).
# --reload watches for file changes, which is what we want in dev.
# Phase 9 (deployment hardening) will split this into a separate,
# non-reloading production command.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
