# Entry point for the backend API. Run with:
#   uvicorn app.main:app --reload
# (the Docker image does this automatically, see backend/Dockerfile)

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import (
    admin,
    admin_clients,
    analyses,
    analysis_images,
    angled_components,
    auth,
    banner,
    chain_components,
    client_admin,
    commodities,
    exports,
    health,
    images,
    internal_logs,
    logs,
    minio_services,
    postgres_services,
    projects,
    reference_data,
    standard_tolerances,
)
from app.core.bootstrap import (
    adopt_default_service_if_needed,
    create_root_admin_if_needed,
    upgrade_initialized_services,
)
from app.core.config import settings
from app.core.email import validate_email_settings
from app.core.logging_config import LOG_RETENTION_DAYS, cleanup_old_logs, configure_logging
from app.core.rate_limit import limiter
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# How often the retention sweep runs after the one at startup. Daily is
# plenty for a 7-day cutoff, and this container is restarted often enough
# that the startup sweep does most of the work anyway.
LOG_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


async def _periodic_log_cleanup() -> None:
    while True:
        await asyncio.sleep(LOG_CLEANUP_INTERVAL_SECONDS)
        try:
            removed = cleanup_old_logs()
            if removed:
                logger.info("Log cleanup removed %d file(s) older than %d days", removed, LOG_RETENTION_DAYS)
        except Exception:
            # A failed sweep must not kill the task -- it would silently
            # stop all future cleanups for the life of the process.
            logger.exception("Scheduled log cleanup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the app starts, before it accepts any requests.
    # Bucket creation for a project's MinIO is no longer done here --
    # buckets are per-service now (core/service_storage.py) and owned by
    # the admin's "Initialize" action on that service, not app startup.

    # First of all, so everything below this line is captured -- including
    # anything that fails during startup, which is exactly what someone
    # will be looking for in the log viewer.
    configure_logging()
    removed = cleanup_old_logs()
    logger.info(
        "Logging to %s; cleanup removed %d file(s) older than %d days",
        settings.log_dir,
        removed,
        LOG_RETENTION_DAYS,
    )

    # Checked before anything else: a bad SMTP config should stop the
    # deploy, not wait to be discovered by the first password reset.
    validate_email_settings()

    db = SessionLocal()
    try:
        create_root_admin_if_needed(db)
        adopt_default_service_if_needed(db)
        # After adoption, so a service adopted just above is included in
        # the same pass rather than waiting for the next restart.
        upgrade_initialized_services(db)
    finally:
        db.close()

    cleanup_task = asyncio.create_task(_periodic_log_cleanup())
    try:
        yield
    finally:
        # Cancelled explicitly so a reload doesn't leave the previous
        # process's task running against the same log directory.
        cleanup_task.cancel()


app = FastAPI(title="StackFit Pro API", lifespan=lifespan)

# Rate limiting for the auth endpoints (see core/rate_limit.py). slowapi
# reads the limiter off app.state, and needs its own handler registered to
# turn an exceeded limit into a 429 instead of an unhandled exception.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    # Without this, an unhandled error becomes a traceback on uvicorn's
    # stdout and nothing else -- invisible to the admin log viewer, and
    # gone entirely the next time the container is rebuilt. Logs the full
    # traceback (secrets stripped by the filter in core/logging_config.py)
    # while returning exactly what FastAPI would have returned, so no
    # internal detail reaches the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal Server Error"},
    )

# Allow the React frontend (running on a different port/origin in dev) to
# call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin_clients.router)
app.include_router(client_admin.router)
app.include_router(postgres_services.router)
app.include_router(minio_services.router)
app.include_router(projects.router)
app.include_router(commodities.router)
app.include_router(analyses.router)
app.include_router(reference_data.router)
app.include_router(images.router)
app.include_router(analysis_images.router)
app.include_router(chain_components.router)
app.include_router(angled_components.router)
app.include_router(standard_tolerances.router)
app.include_router(exports.router)
app.include_router(banner.router)
app.include_router(logs.router)
app.include_router(internal_logs.router)


@app.get("/")
def root():
    return {"message": "StackFit Pro API is running"}
