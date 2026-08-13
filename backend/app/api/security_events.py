# Read-only viewer for the security_events audit trail
# (models/security_event.py) -- root_admin only, across every client.
# See that model's header comment for why root_admin reading this table
# is a deliberate, narrow exception to the tenancy boundary the rest of
# the app enforces (CLAUDE.md), not a precedent for anything else.
#
# Deliberately no POST/PUT/DELETE here -- the table is append-only from
# the application's side (core/security_events.py's record_event, called
# from every route listed in the plan behind this feature); the only
# thing that ever removes a row is the daily retention sweep
# (core/security_events.py's cleanup_old_security_events, wired into
# main.py).

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.db.session import get_db
from app.models.security_event import SecurityEvent
from app.models.user import User
from app.schemas.security_event import SecurityEventsOut

router = APIRouter(prefix="/admin/security-log", tags=["admin"])

# Prefix of event_type, e.g. "auth" matches "auth.login_failed" -- one
# dropdown for the whole category rather than every exact event_type.
EventCategory = Literal["all", "auth", "user", "client", "project", "system", "data", "export"]
OutcomeFilter = Literal["all", "success", "failure"]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@router.get("", response_model=SecurityEventsOut)
def read_security_events(
    category: EventCategory = "all",
    outcome: OutcomeFilter = "all",
    client_id: int | None = None,
    actor_email: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    query = db.query(SecurityEvent)

    if category != "all":
        query = query.filter(SecurityEvent.event_type.like(f"{category}.%"))
    if outcome != "all":
        query = query.filter(SecurityEvent.outcome == outcome)
    if client_id is not None:
        query = query.filter(SecurityEvent.client_id == client_id)
    if actor_email:
        query = query.filter(SecurityEvent.actor_email.ilike(f"%{actor_email}%"))
    if from_date is not None:
        query = query.filter(SecurityEvent.occurred_at >= from_date)
    if to_date is not None:
        query = query.filter(SecurityEvent.occurred_at <= to_date)

    total = query.count()
    # event_id as the tiebreaker: several rows from one bulk action (e.g.
    # delete_client, which can emit more than one event) share the same
    # occurred_at timestamp, and without a second sort key their relative
    # order between pages isn't stable.
    entries = (
        query.order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.event_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return SecurityEventsOut(entries=entries, total=total, page=page, page_size=page_size)
