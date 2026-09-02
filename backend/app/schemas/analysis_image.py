from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.analysis_image import ImageTag


class AnalysisImageOut(BaseModel):
    # object_key (the MinIO path) is deliberately not exposed -- the
    # frontend fetches file bytes via GET /analysis-images/{id}/file.
    model_config = ConfigDict(from_attributes=True)

    analysis_image_id: int
    entry_id: int
    original_filename: str
    content_type: str
    tag: ImageTag
    uploaded_at: datetime


class AnalysisImageTagUpdate(BaseModel):
    tag: ImageTag
