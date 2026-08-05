from pydantic import BaseModel, ConfigDict, field_validator


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
    model_config = ConfigDict(from_attributes=True)

    marker_id: int
    image_id: int
    sequence_number: int
    x: float
    y: float
