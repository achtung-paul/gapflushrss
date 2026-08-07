from pydantic import BaseModel, field_validator


class Point(BaseModel):
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


class MarkerCreate(BaseModel):
    # The polyline the user drew, in the order they clicked it -- the
    # last point is where the numbered marker balloon is placed. At
    # least one point (a "line" the user finished without adding a
    # second vertex) is fine, that's just a marker with no visible line.
    points: list[Point]

    @field_validator("points")
    @classmethod
    def must_have_a_point(cls, value: list[Point]) -> list[Point]:
        if not value:
            raise ValueError("must have at least one point")
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
    points: list[Point]
