# An Analysis under a Commodity. `analysis_code` is the human-facing
# unique ID from the brief (commodity code + zero-padded sequence number,
# e.g. "DR-001"). `sequence_number` is stored separately so working out
# "what's the next number for this commodity" is a simple integer query,
# and the unique constraint on it (per commodity) catches any race
# between two analyses being created for the same commodity at once.
#
# analysis_code is NOT globally unique (it was, until this table became
# project-scoped -- see models/commodity.py). Since Commodity.code is
# only unique per-project, and two different projects can be colocated
# on the same physical Postgres service, two unrelated projects can each
# have their own "IP" commodity and both want "IP-001" as their first
# analysis's code -- that's fine, they're different rows in different
# projects that happen to render the same human-facing label. The
# (commodity_id, sequence_number) constraint below is what actually
# guarantees no duplicate within one commodity.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.project_base import ProjectBase


class Analysis(ProjectBase):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("commodity_id", "sequence_number"),)

    analysis_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commodity_id: Mapped[int] = mapped_column(
        ForeignKey("commodities.commodity_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_code: Mapped[str] = mapped_column(String(20), nullable=False)
    # User-entered label like "IP to Console" -- purely descriptive, no
    # uniqueness or format rules (unlike analysis_code, which is the
    # generated identifier). Defaults to empty rather than nullable so
    # every read path can treat it as a plain string with no None check.
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
