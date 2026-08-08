# One row of an angled-interface tolerance table (direction == OTHER on the
# parent AnalysisEntry -- see core/angled_simulation.py for the maths this
# feeds). Deliberately a separate table from ChainComponent, not two extra
# nullable columns on it:
#
#  - ChainComponent.contributor_type (Component/Process) is NOT NULL and
#    meaningful; an angled row has no such distinction, so forcing a value
#    in would record a fact that isn't one.
#  - ChainComponent.tolerance_value is NOT NULL and read unguarded
#    (api/chain_components.py's get_simulation does float(tolerance_value)
#    with no None check) -- making it nullable to hold angled rows would
#    require a defensive filter on every existing linear read path.
#  - This repo's own "one table, one type column" precedent (AnalysisEntry
#    Gap/Flush, ChainComponent Component/Process) is justified by identical
#    field shape. A single ± magnitude and an X/Y pair are not that.
#
# Kept dormant rather than deleted when an entry's direction is switched
# away from OTHER and back -- nothing needs to filter these out of the
# linear UI or vice versa, since they live in entirely separate tables.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class AngledComponent(ProjectBase):
    __tablename__ = "angled_components"
    __table_args__ = (UniqueConstraint("entry_id", "sequence_number"),)

    angled_component_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_entries.entry_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    component_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Positive ± magnitudes along vehicle X and Y, resolved onto the
    # entry's interface_angle before being combined -- see
    # core/angled_simulation.py's resolve_variations().
    x_tolerance: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    y_tolerance: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)

    # Plain text, same reasoning as ChainComponent.note -- rendered as an
    # ordinary React string, never as markup, so it needs no sanitiser.
    note: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
