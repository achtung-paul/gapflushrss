# Per-client configuration of which RSS confidence levels (1-5 sigma,
# see core/simulation.py) that client's analysis pages show, and whether
# each shown level gets a pass/fail (RAG) verdict or is purely
# informational. Different clients' engineering standards disagree on
# which sigma level(s) actually matter for a sign-off -- this lets each
# client's own admin pick their own model instead of the app assuming
# one for everyone.
#
# Exactly 5 rows per client (sigma_level 1-5), always -- seeded at
# client creation (api/admin_clients.py's create_client) and backfilled
# for every pre-existing client by this table's own migration. Nothing
# reads this table with a fallback for a missing row; every caller
# assumes the invariant holds.

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StatisticalModelSetting(Base):
    __tablename__ = "statistical_model_settings"
    __table_args__ = (UniqueConstraint("client_id", "sigma_level", name="uq_stat_model_setting_client_sigma"),)

    statistical_model_setting_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.client_id", ondelete="CASCADE"), nullable=False
    )
    sigma_level: Mapped[int] = mapped_column(Integer, nullable=False)
    # Whether this level appears at all on analysis pages for this client.
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Only meaningful when visible=True: shows the predicted spread with
    # no RAG badge, since it isn't a level this client signs off against.
    info_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
