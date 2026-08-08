from pydantic import BaseModel, ConfigDict, field_validator

from app.models.chain_component import ContributorType


class ChainComponentCreate(BaseModel):
    contributor_type: ContributorType
    description: str
    # The +/-3 sigma tolerance magnitude for this contributor -- see
    # app/core/simulation.py for how this gets combined with the rest
    # of the chain.
    tolerance_value: float
    # Optional: which cell of the admin tolerance matrix (Phase 3) this
    # value was prefilled from, purely for traceability.
    tolerance_value_id: int | None = None
    # Plain text, not markup -- rendered as an ordinary React string.
    note: str = ""
    # An actual measured value in mm, distinct from tolerance_value.
    # Optional -- not every contributor has been physically measured yet.
    measured_value: float | None = None
    # Plain text, not markup -- rendered as an ordinary React string.
    material: str = ""

    @field_validator("note")
    @classmethod
    def note_must_fit(cls, value: str) -> str:
        # Matches the column width so an over-long note is a clean 422
        # rather than a database error.
        if len(value) > 500:
            raise ValueError("note must be 500 characters or fewer")
        return value

    @field_validator("material")
    @classmethod
    def material_must_fit(cls, value: str) -> str:
        if len(value) > 255:
            raise ValueError("material must be 255 characters or fewer")
        return value

    @field_validator("tolerance_value")
    @classmethod
    def must_not_be_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("tolerance_value must be given as a positive magnitude")
        return value

    @field_validator("description")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("description must not be blank")
        return value


class ChainComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_component_id: int
    entry_id: int
    sequence_number: int
    contributor_type: ContributorType
    description: str
    tolerance_value: float
    tolerance_value_id: int | None
    note: str
    measured_value: float | None
    material: str
    # Server-resolved from tolerance_value_id, not client-settable --
    # see models/chain_component.py. Absent from ChainComponentCreate on
    # purpose.
    tolerance_group_name: str | None


class SimulationResultRow(BaseModel):
    sigma_level: int
    spread: float
    lower_bound: float
    upper_bound: float
    rag: str


class SimulationResultOut(BaseModel):
    # The combined 1 sigma value across the whole chain, before scaling
    # to any particular confidence level -- exposed directly so the
    # frontend doesn't have to reverse it out of spread/sigma_level.
    sigma_1: float
    results: list[SimulationResultRow]
