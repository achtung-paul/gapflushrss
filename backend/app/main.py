# Entry point for the backend API. Run with:
#   uvicorn app.main:app --reload
# (the Docker image does this automatically, see backend/Dockerfile)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    analyses,
    analysis_images,
    auth,
    chain_components,
    commodities,
    health,
    images,
    minio_services,
    postgres_services,
    projects,
    reference_data,
    standard_tolerances,
)
from app.core.bootstrap import (
    adopt_default_service_if_needed,
    create_default_process_types_if_needed,
    create_root_admin_if_needed,
)
from app.core.config import settings
from app.db.session import SessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the app starts, before it accepts any requests.
    # Bucket creation for a project's MinIO is no longer done here --
    # buckets are per-service now (core/service_storage.py) and owned by
    # the admin's "Initialize" action on that service, not app startup.
    db = SessionLocal()
    try:
        create_root_admin_if_needed(db)
        create_default_process_types_if_needed(db)
        adopt_default_service_if_needed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="GapFlushRSS API", lifespan=lifespan)

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
app.include_router(postgres_services.router)
app.include_router(minio_services.router)
app.include_router(projects.router)
app.include_router(commodities.router)
app.include_router(analyses.router)
app.include_router(reference_data.router)
app.include_router(images.router)
app.include_router(analysis_images.router)
app.include_router(chain_components.router)
app.include_router(standard_tolerances.router)


@app.get("/")
def root():
    return {"message": "GapFlushRSS API is running"}
