from pydantic import BaseModel, ConfigDict, field_validator

from app.models.analysis_entry import CalculationMethod


class AngledComponentCreate(BaseModel):
    component_name: str
    # Positive +/- magnitudes along vehicle X and Y, resolved onto the
    # entry's interface_angle -- see app/core/angled_simulation.py.
    x_tolerance: float
    y_tolerance: float
    # Plain text, not markup -- rendered as an ordinary React string.
    note: str = ""

    @field_validator("note")
    @classmethod
    def note_must_fit(cls, value: str) -> str:
        # Matches the column width so an over-long note is a clean 422
        # rather than a database error.
        if len(value) > 500:
            raise ValueError("note must be 500 characters or fewer")
        return value

    @field_validator("x_tolerance", "y_tolerance")
    @classmethod
    def must_not_be_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("tolerance must be given as a positive magnitude")
        return value

    @field_validator("component_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("component_name must not be blank")
        return value


class AngledComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    angled_component_id: int
    entry_id: int
    sequence_number: int
    component_name: str
    x_tolerance: float
    y_tolerance: float
    note: str


class AngledSimulationRow(BaseModel):
    angled_component_id: int
    component_name: str
    x_tolerance: float
    y_tolerance: float
    # The resolved contribution along the interface -- x_tolerance *
    # cos(angle) and y_tolerance * sin(angle) respectively. Exposed so the
    # frontend can show the transformation instead of re-deriving it.
    vx: float
    vy: float


class AngledSimulationOut(BaseModel):
    interface_angle: float
    calculation_method: CalculationMethod
    total_variation: float
    lower_bound: float
    upper_bound: float
    rag: str
    rows: list[AngledSimulationRow]
