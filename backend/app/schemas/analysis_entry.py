from pydantic import BaseModel, field_validator, model_validator

from app.models.analysis_entry import CalculationMethod, Direction, EntryType


class AnalysisEntryCreate(BaseModel):
    # e.g. nominal=3.5, upper_limit=1, lower_limit=0.2 means the
    # acceptable band is 3.3 to 4.5. Supports the brief's asymmetric
    # tolerances (e.g. +0/-0.5) since upper and lower are independent.
    #
    # Storage (and every calculation downstream -- core/simulation.py,
    # exports, reports) always uses upper_limit/lower_limit as positive
    # magnitudes; there is exactly one representation on disk. A caller
    # may instead send upper_bound/lower_bound -- the actual signed band
    # edges -- which resolve_limits below converts to magnitudes before
    # anything else ever sees them. This is for compressible-material
    # targets, where the whole band (nominal included) can be negative,
    # e.g. nominal=-0.5, band -1.0 to -0.1: typing that directly as
    # upper_bound=-0.1/lower_bound=-1.0 is the natural way to think about
    # it, versus first hand-computing magnitudes of 0.4 and 0.5.
    nominal_value: float
    upper_limit: float | None = None
    lower_limit: float | None = None
    upper_bound: float | None = None
    lower_bound: float | None = None
    direction: Direction | None = None
    # Rich text from the notes editor, as HTML. Defaulted so existing
    # clients that don't send it keep working. Sanitised in
    # api/analyses.py before it is stored -- never trust this value.
    notes: str = ""

    @model_validator(mode="after")
    def resolve_limits(self) -> "AnalysisEntryCreate":
        magnitudes_given = self.upper_limit is not None or self.lower_limit is not None
        bounds_given = self.upper_bound is not None or self.lower_bound is not None
        if magnitudes_given and bounds_given:
            raise ValueError("Provide either upper_limit/lower_limit or upper_bound/lower_bound, not both")

        if bounds_given:
            if self.upper_bound is None or self.lower_bound is None:
                raise ValueError("upper_bound and lower_bound must both be given together")
            if self.upper_bound < self.nominal_value:
                raise ValueError("upper_bound must be at or above the nominal value")
            if self.lower_bound > self.nominal_value:
                raise ValueError("lower_bound must be at or below the nominal value")
            # Converted immediately, not stored as-is -- see the class
            # comment above. upper_bound/lower_bound themselves are
            # never persisted; AnalysisEntryOut recomputes them for
            # display from whichever representation is on file.
            self.upper_limit = self.upper_bound - self.nominal_value
            self.lower_limit = self.nominal_value - self.lower_bound
        else:
            if self.upper_limit is None or self.lower_limit is None:
                raise ValueError("upper_limit and lower_limit must both be given")
            if self.upper_limit < 0 or self.lower_limit < 0:
                raise ValueError("limits must be given as positive magnitudes")
        return self


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
    # Computed, not stored -- the signed band edges (nominal +/-
    # upper_limit/lower_limit), for a consumer that wants to display or
    # re-edit an entry in absolute terms (see AnalysisEntryCreate's
    # upper_bound/lower_bound) without redoing that arithmetic itself.
    upper_bound: float
    lower_bound: float
    direction: Direction | None
    created_by_name: str
    updated_by_name: str
    # Already sanitised when it was stored, which is what makes it safe
    # for the frontend to render as markup.
    notes: str
    # Angled-interface settings -- only meaningful when direction is
    # OTHER, but always present (see models/analysis_entry.py). Saved via
    # a dedicated endpoint (AngledSettingsUpdate below), not this schema --
    # AnalysisEntryCreate is deliberately left without these fields, since
    # AnalysisListPage.jsx's inline edit form already omits `notes` from
    # its PUT body and silently resets it; adding more defaulted fields
    # here would let the same trap reset the angle too.
    interface_angle: float
    calculation_method: CalculationMethod


class AngledSettingsUpdate(BaseModel):
    interface_angle: float
    calculation_method: CalculationMethod

    @field_validator("interface_angle")
    @classmethod
    def angle_must_be_in_range(cls, value: float) -> float:
        # Outside 0-90, cos(theta) goes negative and would *reduce* the
        # worst-case total -- a sign error masquerading as a result.
        if not (0 <= value <= 90):
            raise ValueError("interface_angle must be between 0 and 90 degrees")
        return value
