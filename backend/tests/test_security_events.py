# Tests for the security-event audit trail: core/security_events.py's
# record_event() and cleanup_old_security_events().
#
# Same conventions as test_tenancy.py / test_two_factor.py: db_session
# (conftest.py) for anything that needs a real query; functions called
# directly rather than through FastAPI DI, since there's no TestClient
# fixture in this suite.

from datetime import datetime, timedelta, timezone

from app.core.security_events import (
    EVENT_LOGIN_FAILED,
    EVENT_LOGIN_SUCCESS,
    cleanup_old_security_events,
    record_event,
)
from app.models.security_event import SecurityEvent
from app.models.user import GlobalRole, User


def _make_user(db_session, email="user@example.com", client_id=None):
    user = User(
        first_name="Test",
        last_name="User",
        email=email,
        password_hash="x",
        global_role=GlobalRole.standard,
        client_id=client_id,
    )
    db_session.add(user)
    db_session.flush()
    return user


# --- record_event ------------------------------------------------------


def test_record_event_writes_row_from_actor(db_session):
    user = _make_user(db_session)
    record_event(
        db_session,
        event_type=EVENT_LOGIN_SUCCESS,
        actor=user,
        target_type="user",
        target_id=user.user_id,
        target_name=user.email,
    )
    db_session.flush()

    row = db_session.query(SecurityEvent).one()
    assert row.event_type == EVENT_LOGIN_SUCCESS
    assert row.outcome == "success"
    assert row.actor_user_id == user.user_id
    assert row.actor_email == user.email
    assert row.actor_name == "Test User"
    assert row.actor_role == "standard"


def test_record_event_falls_back_to_actor_email_when_no_actor(db_session):
    # The unknown-email login-failure case -- there is no User row to
    # point at, only the address that was tried.
    record_event(
        db_session,
        event_type=EVENT_LOGIN_FAILED,
        outcome="failure",
        actor_email="nobody@example.com",
    )
    db_session.flush()

    row = db_session.query(SecurityEvent).one()
    assert row.actor_user_id is None
    assert row.actor_email == "nobody@example.com"
    assert row.actor_name == ""


class _BrokenSession:
    """Stands in for a Session whose add() always fails -- forces
    record_event's write to fail deterministically, regardless of what a
    real database would or wouldn't reject (SQLite, used by db_session,
    doesn't enforce column length the way Postgres does).
    """

    def add(self, obj):
        raise RuntimeError("boom")


def test_record_event_never_raises_on_write_failure():
    # A bug in audit logging must not be able to take down the action it
    # is merely observing (a login, a delete, ...) -- the whole point of
    # record_event's own try/except.
    record_event(_BrokenSession(), event_type=EVENT_LOGIN_SUCCESS)  # must not raise


def test_deleting_user_leaves_event_intact(db_session):
    # The whole point of the no-FK design (see models/security_event.py)
    # -- an event about a user must survive that user being deleted.
    user = _make_user(db_session)
    record_event(db_session, event_type=EVENT_LOGIN_SUCCESS, actor=user)
    db_session.flush()

    db_session.delete(user)
    db_session.flush()

    row = db_session.query(SecurityEvent).one()
    assert row.actor_email == "user@example.com"
    assert row.actor_name == "Test User"


# --- retention sweep -----------------------------------------------------


def test_cleanup_removes_only_events_past_retention(db_session):
    now = datetime.now(timezone.utc)
    old_event = SecurityEvent(
        event_type=EVENT_LOGIN_SUCCESS, occurred_at=now - timedelta(days=361)
    )
    recent_event = SecurityEvent(
        event_type=EVENT_LOGIN_SUCCESS, occurred_at=now - timedelta(days=359)
    )
    db_session.add_all([old_event, recent_event])
    db_session.commit()

    removed = cleanup_old_security_events(db_session)

    assert removed == 1
    remaining = db_session.query(SecurityEvent).all()
    assert len(remaining) == 1
    assert remaining[0].event_id == recent_event.event_id
