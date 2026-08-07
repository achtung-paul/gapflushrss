from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    project_name: str
    # Which Postgres/MinIO this project's Commodity-and-below data will
    # live on -- picked once, from the admin's list of already-initialized
    # services (see api/postgres_services.py, api/minio_services.py).
    # There's no update path: moving a live project to a different
    # physical service would mean copying all its data, which isn't
    # supported.
    postgres_service_id: int
    minio_service_id: int


class ProjectUpdate(BaseModel):
    project_name: str


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    project_name: str
    postgres_service_id: int
    minio_service_id: int
    # The calling user's role on this specific project ("Root Admin",
    # "Manager", "Contributor", or "Viewer") -- built by hand per-request
    # in api/projects.py, not a column on Project, since it depends on
    # who's asking.
    my_role: str
