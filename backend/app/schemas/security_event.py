# Response shapes for GET /admin/security-log (api/security_events.py).
# No request/update schema -- the route is read-only by design, see that
# module's header comment.

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SecurityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    occurred_at: datetime
    event_type: str
    outcome: str
    actor_user_id: int | None
    actor_email: str
    actor_name: str
    actor_role: str | None
    client_id: int | None
    client_name: str | None
    source_ip: str | None
    target_type: str | None
    target_id: int | None
    target_name: str | None
    detail: str | None


class SecurityEventsOut(BaseModel):
    # A page of events plus the total count matching the filters, so the
    # frontend can render "page X of Y" without a second request -- same
    # shape as schemas/user.py's UserListOut.
    entries: list[SecurityEventOut]
    total: int
    page: int
    page_size: int
