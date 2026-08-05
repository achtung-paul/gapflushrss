from pydantic import BaseModel, ConfigDict

from app.schemas.analysis_entry import AnalysisEntryOut


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: int
    commodity_id: int
    analysis_code: str
    sequence_number: int


class AnalysisDetailOut(AnalysisOut):
    # None until someone attaches that entry (see api/analyses.py) --
    # an Analysis can exist as a placeholder with neither yet, per the brief.
    gap: AnalysisEntryOut | None = None
    flush: AnalysisEntryOut | None = None
