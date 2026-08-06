from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImageOut(BaseModel):
    # object_key (the MinIO path) is deliberately not exposed -- the
    # frontend fetches file bytes via GET /images/{image_id}/file instead.
    model_config = ConfigDict(from_attributes=True)

    image_id: int
    commodity_id: int
    original_filename: str
    content_type: str
    uploaded_at: datetime
