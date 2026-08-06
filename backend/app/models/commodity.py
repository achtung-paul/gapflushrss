# Commodity(name, code) under a Project, per PROJECT_BRIEF.md's data
# hierarchy: Project -> Commodity -> Analysis. `code` is the 2-letter
# prefix (e.g. "DR" for Doors) used to build each Analysis's unique ID,
# so it has to be unique across the whole system, not just this project --
# otherwise two commodities with the same code could generate colliding
# Analysis IDs.

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Commodity(Base):
    __tablename__ = "commodities"

    commodity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
