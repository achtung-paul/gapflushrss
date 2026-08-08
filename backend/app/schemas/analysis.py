from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.analysis_entry import AnalysisEntryOut


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    commodity_id: int
    analysis_code: str
    sequence_number: int
    description: str


class AnalysisDetailOut(AnalysisOut):
    # None until someone attaches that entry (see api/analyses.py) --
    # an Analysis can exist as a placeholder with neither yet, per the brief.
    gap: AnalysisEntryOut | None = None
    flush: AnalysisEntryOut | None = None


class AnalysisUpdate(BaseModel):
    # Its own narrow body rather than folded into a full-replace schema --
    # same reasoning as AngledSettingsUpdate in analysis_entry.py: two
    # different pages (AnalysisDetailPage and AnalysisListPage) would each
    # need to know every other field just to avoid resetting it.
    description: str

    @field_validator("description")
    @classmethod
    def description_must_fit(cls, value: str) -> str:
        if len(value) > 255:
            raise ValueError("Description must be 255 characters or fewer")
        return value
