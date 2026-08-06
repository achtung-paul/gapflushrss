from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    project_name: str


class ProjectUpdate(BaseModel):
    project_name: str


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    project_name: str
