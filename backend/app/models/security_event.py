# An append-only audit trail: logins (success/failure), logouts, 2FA
# events, permission changes, user/client lifecycle, data deletion, and
# Excel exports. Built for one purpose -- tracing a security incident,
# per the plan behind this feature: without login details, the areas an
# intrusion reached, and its source IP, an incident can't be
# reconstructed after the fact.
#
# EXCEPTION TO THE TENANCY BOUNDARY, DELIBERATE AND NARROW: api/deps.py's
# three tenancy helpers (see CLAUDE.md) exist so root_admin can never
# read a client's users, projects, or data. This table is read by
# root_admin across every client (api/security_events.py's
# read_security_events, require_root_admin only) -- an event here
# necessarily names a client's user and what they touched, which is
# exactly the incident-response information root_admin would otherwise
# have no way to get. This exception applies to this table ONLY. It must
# never be used as precedent to add a root_admin path into a client's
# projects, tolerance matrix, or analysis data anywhere else -- if a
# future route reads security_events and also joins out to real client
# data, that route is the bug this comment is warning about.
#
# Client_admins get no view of this table in this version -- see the
# plan file for the "root_admin only" decision.
#
# Every actor/target field is denormalised -- first_name/last_name/email
# copied at the time of the event, never a foreign key. This is the
# opposite of the rest of the app's style (see CLAUDE.md's FK
# conventions) and is deliberate: the whole point of an audit row is
# that it outlives the thing it describes. A real FK to users.user_id
# would either block deleting the very user a "user.deleted" row is
# about, or (with a cascade) delete the evidence along with them -- both
# wrong for an audit log. This mirrors and extends the existing
# Banner.updated_by_name / SecuritySetting.updated_by_name precedent
# (denormalised actor name, no FK) to the target side too.
#
# Lives in the central database -- every project-scoped route already
# holds a central `db` session for its permission check (see
# api/deps.py's get_project_db), and the per-project databases are
# per-tenant with their own separate migration chain (alembic_project/);
# a log spread across them could never be read back as one timeline.

from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# How long an event is kept before the daily sweep (core/security_events.py's
# cleanup_old_security_events, wired into main.py alongside the unrelated
# 7-day operational-log sweep) removes it. Deliberately a much longer,
# separate retention period from LOG_RETENTION_DAYS
# (core/logging_config.py) -- that constant governs file-based error/warning
# logs used for day-to-day debugging; this one governs the evidence an
# incident investigation needs, potentially long after the fact. The two
# must not be unified.
SECURITY_EVENT_RETENTION_DAYS = 360
SECURITY_EVENT_RETENTION = timedelta(days=SECURITY_EVENT_RETENTION_DAYS)

# Max length of an IPv6 literal written out in full
# ("0000:0000:0000:0000:0000:0000:0000:0000"), the widest value
# core/rate_limit.py's client_ip() can hand back.
_MAX_IP_LENGTH = 45


class SecurityEvent(Base):
    __tablename__ = "security_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    # A dotted string like "auth.login_failed" or "user.deleted" -- see
    # core/security_events.py's EVENT_* constants, which are the only
    # values ever written here (never a hand-typed literal at a call
    # site, so a typo is an ImportError, not a row that silently never
    # matches a filter).
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # "success" or "failure" -- lets the UI badge a row red without the
    # viewer needing to know every event_type's meaning up front.
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")

    # Who did this. actor_user_id is NULL for a failed login against an
    # email address that doesn't belong to any account -- there is no
    # user to point at, but the attempted address (actor_email) is still
    # exactly the thing an investigation needs.
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    actor_name: Mapped[str] = mapped_column(String(201), nullable=False, default="")
    # The actor's global_role at the time of the event ("root_admin" /
    # "client_admin" / "standard") -- copied, not looked up later, since
    # a role can change (or the account can be deleted) after the event
    # is recorded.
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Which client this event concerned, if any -- NULL for a
    # root_admin-only event (creating another root_admin, an unknown-email
    # login failure, the system-wide 2FA toggle). Lets the viewer filter
    # to one client without joining out to the (possibly since-deleted)
    # Client row.
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    client_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # core/rate_limit.py's client_ip(request) -- nginx sets X-Real-IP from
    # $remote_addr, overwriting anything the client sent, so this can't be
    # forged by whoever is making the request.
    source_ip: Mapped[str | None] = mapped_column(String(_MAX_IP_LENGTH), nullable=True)

    # What was acted on, if this event has a target distinct from the
    # actor (e.g. an admin deleting a *different* user). target_name is
    # the client-chosen name captured at the moment of the action --
    # deliberately read before a delete, not derived afterward, since
    # after a delete there is nothing left to derive it from.
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Short free-text extra context (e.g. which role a user was changed
    # to/from) -- not a substitute for target_name/event_type, just room
    # for the one extra fact a specific event type needs.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
