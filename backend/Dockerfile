FROM python:3.13.12-slim

WORKDIR /app

# Makes "import app.xyz" work no matter how a command is invoked in this
# image (uvicorn resolves it from the cwd automatically; plain `alembic`
# does not, since it isn't run as `python -m`).
ENV PYTHONPATH=/app

# Install dependencies first so Docker can cache this layer when only
# application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY alembic_project ./alembic_project
COPY alembic_project.ini .
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
