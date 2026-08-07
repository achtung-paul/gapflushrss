from pydantic import BaseModel, field_validator

from app.models.analysis_entry import Direction, EntryType


class AnalysisEntryCreate(BaseModel):
    # e.g. nominal=3.5, upper_limit=1, lower_limit=0.2 means the
    # acceptable band is 3.3 to 4.5. Supports the brief's asymmetric
    # tolerances (e.g. +0/-0.5) since upper and lower are independent.
    nominal_value: float
    upper_limit: float
    lower_limit: float
    direction: Direction | None = None
    # Rich text from the notes editor, as HTML. Defaulted so existing
    # clients that don't send it keep working. Sanitised in
    # api/analyses.py before it is stored -- never trust this value.
    notes: str = ""

    @field_validator("upper_limit", "lower_limit")
    @classmethod
    def limits_must_not_be_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("limits must be given as positive magnitudes")
        return value


class AnalysisEntryOut(BaseModel):
    # Built by hand in api/analyses.py (not read straight off the ORM
    # object), since entry_code is computed from the parent Analysis's
    # analysis_code rather than being a column on this table.
    entry_id: int
    analysis_id: int
    entry_type: EntryType
    entry_code: str
    nominal_value: float
    upper_limit: float
    lower_limit: float
    direction: Direction | None
    created_by_name: str
    updated_by_name: str
    # Already sanitised when it was stored, which is what makes it safe
    # for the frontend to render as markup.
    notes: str
