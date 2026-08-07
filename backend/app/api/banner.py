# The site-wide notice shown to every logged-in user (see
# models/banner.py for why it's a single row).
#
# Two different audiences, so two different guards:
#   GET  /banner        -- any logged-in user, because everyone sees it
#   PUT  /admin/banner  -- root admin only, because anyone who can write
#                          here can put text in front of every user
#
# Both live in this one module since they're the same resource; the paths
# differ so the admin one sits with the rest of /admin.

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_root_admin
from app.db.session import get_db
from app.models.banner import BANNER_ID, Banner, BannerColour
from app.models.user import User
from app.schemas.banner import BannerOut, BannerUpdate

router = APIRouter(tags=["banner"])


def _get_or_create_banner(db: Session) -> Banner:
    """The one banner row, created empty and inactive on first access.

    Created here rather than seeded by the migration so there's no
    ordering dependency between the two, and so a deployment whose row was
    deleted by hand recovers on its own instead of 500ing.
    """
    banner = db.get(Banner, BANNER_ID)
    if banner is None:
        banner = Banner(
            banner_id=BANNER_ID,
            message="",
            colour=BannerColour.blue,
            is_active=False,
            updated_by_name="",
        )
        db.add(banner)
        db.commit()
        db.refresh(banner)
    return banner


@router.get("/banner", response_model=BannerOut)
def read_banner(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    # Any logged-in user: this is what they're meant to see. Note it's
    # still behind authentication -- a notice about, say, planned downtime
    # shouldn't be readable by anyone who happens to hit the URL.
    return _get_or_create_banner(db)


@router.put("/admin/banner", response_model=BannerOut)
def update_banner(
    body: BannerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
):
    banner = _get_or_create_banner(db)
    banner.message = body.message.strip()
    banner.colour = body.colour
    banner.is_active = body.is_active
    # Bumped on every save, including one that only toggles is_active.
    # The frontend keys dismissals on this, so any change re-shows the
    # banner to users who had already closed the previous version.
    banner.updated_at = datetime.now(timezone.utc)
    banner.updated_by_name = f"{current_user.first_name} {current_user.last_name}"
    db.commit()
    db.refresh(banner)
    return banner
