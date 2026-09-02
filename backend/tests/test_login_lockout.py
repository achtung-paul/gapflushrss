# Tests for core/login_lockout.py's per-account brute-force counter,
# shared by the password step and the 2FA step of login (api/auth.py).
#
# Same conventions as test_two_factor.py / test_security_events.py:
# db_session (conftest.py), a local _make_user, functions called
# directly rather than through FastAPI DI. login()/verify_2fa() aren't
# exercised directly here (no TestClient/Request fixture in this suite,
# and verify_2fa is wrapped by slowapi's rate-limit decorator) -- what's
# tested is the same register_failure/clear_failures call those routes
# make, which is where the actual lockout logic lives.

from datetime import datetime, timedelta, timezone

from app.core.login_lockout import FAILURE_WINDOW, MAX_FAILURES, clear_failures, is_locked, register_failure
from app.models.user import GlobalRole, User


def _make_user(db_session, email="user@example.com"):
    user = User(
        first_name="Test",
        last_name="User",
        email=email,
        password_hash="x",
        global_role=GlobalRole.standard,
        client_id=None,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_register_failure_increments_count(db_session):
    user = _make_user(db_session)
    assert user.failed_auth_count == 0

    register_failure(db_session, user)
    assert user.failed_auth_count == 1
    assert user.last_failed_auth_at is not None
    assert is_locked(user) is False


def test_register_failure_locks_on_the_max_failures_th_attempt(db_session):
    user = _make_user(db_session)

    for _ in range(MAX_FAILURES - 1):
        locked = register_failure(db_session, user)
        assert locked is False

    locked = register_failure(db_session, user)
    assert locked is True
    assert user.failed_auth_count == MAX_FAILURES
    assert is_locked(user) is True


def test_register_failure_older_than_the_window_restarts_the_count(db_session):
    user = _make_user(db_session)
    user.failed_auth_count = 5
    user.last_failed_auth_at = datetime.now(timezone.utc) - FAILURE_WINDOW - timedelta(minutes=1)
    db_session.flush()

    register_failure(db_session, user)

    assert user.failed_auth_count == 1


def test_register_failure_within_the_window_keeps_counting(db_session):
    user = _make_user(db_session)
    user.failed_auth_count = 5
    user.last_failed_auth_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.flush()

    register_failure(db_session, user)

    assert user.failed_auth_count == 6


def test_register_failure_is_a_no_op_once_locked(db_session):
    user = _make_user(db_session)
    user.failed_auth_count = MAX_FAILURES
    user.locked_at = datetime.now(timezone.utc)
    db_session.flush()

    locked_again = register_failure(db_session, user)

    assert locked_again is False
    assert user.failed_auth_count == MAX_FAILURES  # unchanged, not incremented further


def test_clear_failures_resets_count_and_lifts_lock(db_session):
    user = _make_user(db_session)
    user.failed_auth_count = MAX_FAILURES
    user.last_failed_auth_at = datetime.now(timezone.utc)
    user.locked_at = datetime.now(timezone.utc)
    db_session.flush()

    clear_failures(db_session, user)

    assert user.failed_auth_count == 0
    assert user.last_failed_auth_at is None
    assert user.locked_at is None
    assert is_locked(user) is False
