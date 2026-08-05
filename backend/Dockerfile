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

EXPOSE 8000

# Apply any pending database migrations, then start the server.
# --reload watches for file changes, which is what we want in dev.
# Phase 9 (deployment hardening) will split this into a separate,
# non-reloading production command.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
