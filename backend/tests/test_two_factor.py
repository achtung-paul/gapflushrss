# Tests for the account-security work: password policy (min length +
# common-password screening), the must_reset_password flag that replaced
# the old rolling password expiry, the system-wide 2FA toggle, and TOTP
# code verification/replay protection (core/totp.py).
#
# Same conventions as test_tenancy.py: db_session (conftest.py) only
# where a real query matters; dependency functions called directly by
# supplying their Depends() defaults by hand.

import pytest

from app.api.security_settings import get_or_create_security_settings
from app.core.security import force_password_reset, validate_password_strength
from app.core.totp import TOTP_STEP_SECONDS, current_step, generate_secret, verify_code
from app.models.security_setting import SecuritySetting
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession


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


# --- password policy -------------------------------------------------


def test_validate_password_strength_rejects_common_password():
    # "welcome123456" is in the bundled wordlist (data/common_passwords.txt)
    # -- 13 characters, so it clears the length rule on its own and would
    # otherwise pass.
    with pytest.raises(ValueError):
        validate_password_strength("welcome123456")


def test_validate_password_strength_rejects_common_password_case_insensitively():
    # Capitalising a letter shouldn't be enough to dodge the screen --
    # see breached_passwords.py's is_commonly_breached lowercasing.
    with pytest.raises(ValueError):
        validate_password_strength("WELCOME123456")


def test_validate_password_strength_accepts_strong_password():
    # Long, not in the wordlist, under the 72-byte bcrypt ceiling.
    validate_password_strength("Xk9#mQ2vLp7$wRz4")


def test_validate_password_strength_rejects_too_short():
    with pytest.raises(ValueError):
        validate_password_strength("Short1!")


# --- must_reset_password (replaces the old PASSWORD_EXPIRY check) ----


def test_force_password_reset_sets_flag_and_clears_sessions(db_session):
    user = _make_user(db_session)
    assert user.must_reset_password is False

    session = UserSession(session_token="tok123", user_id=user.user_id)
    db_session.add(session)
    db_session.flush()

    force_password_reset(db_session, user)
    db_session.flush()

    assert user.must_reset_password is True
    remaining = db_session.query(UserSession).filter(UserSession.user_id == user.user_id).count()
    assert remaining == 0


# --- system-wide 2FA toggle -------------------------------------------


def test_get_or_create_security_settings_defaults_to_off(db_session):
    row = get_or_create_security_settings(db_session)
    assert row.require_2fa is False

    # Second call must return the same row, not a duplicate -- the
    # fixed-id singleton pattern (models/security_setting.py).
    again = get_or_create_security_settings(db_session)
    assert again.security_settings_id == row.security_settings_id
    assert db_session.query(SecuritySetting).count() == 1


# --- TOTP verification and replay protection ---------------------------


def test_totp_verify_code_accepts_a_currently_valid_code():
    secret = generate_secret()
    import pyotp

    code = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS).now()
    matched_step = verify_code(secret, code, last_used_step=None)
    assert matched_step is not None
    assert matched_step == current_step()


def test_totp_verify_code_rejects_wrong_code():
    secret = generate_secret()
    assert verify_code(secret, "000000", last_used_step=None) is None


def test_totp_verify_code_rejects_replay_of_the_same_step():
    secret = generate_secret()
    import pyotp

    code = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS).now()
    first = verify_code(secret, code, last_used_step=None)
    assert first is not None
    # Same code, same step, presented again -- must be refused now that
    # last_used_step records the step it was already accepted for.
    second = verify_code(secret, code, last_used_step=first)
    assert second is None


def test_totp_verify_code_accepts_one_step_of_clock_drift():
    secret = generate_secret()
    import pyotp

    totp = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS)
    previous_step_time = (current_step() - 1) * TOTP_STEP_SECONDS
    drifted_code = totp.at(previous_step_time)
    matched_step = verify_code(secret, drifted_code, last_used_step=None)
    assert matched_step == current_step() - 1


def test_totp_verify_code_rejects_two_steps_of_clock_drift():
    secret = generate_secret()
    import pyotp

    totp = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS)
    old_step_time = (current_step() - 2) * TOTP_STEP_SECONDS
    old_code = totp.at(old_step_time)
    assert verify_code(secret, old_code, last_used_step=None) is None
