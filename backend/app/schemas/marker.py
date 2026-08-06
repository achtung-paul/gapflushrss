from pydantic import BaseModel, field_validator


class MarkerCreate(BaseModel):
    # Fraction (0-1) of the image's natural width/height -- see
    # app/models/marker.py for why.
    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def must_be_within_image(cls, value: float) -> float:
        if not (0 <= value <= 1):
            raise ValueError("must be between 0 and 1 (a fraction of the image size)")
        return value


class MarkerOut(BaseModel):
    # Built by hand in app/api/images.py (via _marker_out), not
    # model_validate'd straight off a Marker row -- analysis_id,
    # analysis_code, and sequence_number all come from the Marker's
    # linked Analysis, not from a column on Marker itself.
    marker_id: int
    image_id: int
    analysis_id: int
    analysis_code: str
    sequence_number: int
    x: float
    y: float
