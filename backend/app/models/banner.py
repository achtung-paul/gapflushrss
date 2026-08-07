# A site-wide notice a root admin can put in front of every logged-in
# user -- planned downtime, a data issue, "the L366 numbers are being
# re-baselined", that sort of thing.
#
# Deliberately a single row rather than a table of banners with one marked
# active. There is only ever one banner, so "the banner" is a single row
# with a fixed id: no "which one is current?" query, no way to end up with
# two active at once, and editing is a plain update. api/banner.py creates
# it on first access (see _get_or_create_banner).
#
# Lives in the central database, not a project one: it is shown to every
# user on every page, regardless of which project they are looking at.

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The fixed primary key of the one and only banner row.
BANNER_ID = 1


class BannerColour(str, enum.Enum):
    red = "red"
    amber = "amber"
    green = "green"
    blue = "blue"


class Banner(Base):
    __tablename__ = "banner"

    banner_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Plain text, not HTML -- rendered by React as an ordinary string, so
    # unlike AnalysisEntry.notes it carries no markup and needs no
    # sanitising. A banner should be short and legible; a second HTML sink
    # isn't worth the risk it adds.
    message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    colour: Mapped[BannerColour] = mapped_column(
        Enum(BannerColour, name="banner_colour"), nullable=False, default=BannerColour.blue
    )
    # Lets an admin switch the banner off without losing the wording.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # The frontend keys each user's "dismissed" flag on this value, so
    # changing the banner in any way makes it reappear for everyone who
    # had already closed it (see frontend/src/components/Banner.jsx).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_by_name: Mapped[str] = mapped_column(String(201), nullable=False, server_default="")
