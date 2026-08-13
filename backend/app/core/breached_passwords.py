# A common/breached-password screen -- the NIST SP 800-63B recommended
# replacement for composition rules (see core/security.py's
# validate_password_strength). Rejects a password that matches a known
# weak or frequently-reused one, rather than forcing arbitrary
# upper/lower/digit/symbol combinations that just push users toward
# predictable variants of the same password.
#
# Deliberately an offline, bundled wordlist rather than a live call to a
# service like Have I Been Pwned's k-anonymity API. This backend can run
# in an LXC with no outbound internet, and a network call inside password
# validation forces an unpleasant choice on every account creation and
# password change: fail open (the screen silently stops protecting
# anyone) or fail closed (an API outage blocks every password change in
# the app). A bundled list has neither failure mode.
#
# data/common_passwords.txt is a curated list of common password roots
# (password, welcome, letmein, qwerty, ...) crossed with the numeric/
# punctuation suffixes and capitalisation people commonly add to satisfy
# a length rule (Password123!, Welcome2025, ...), filtered to entries at
# least 10 characters long -- anything shorter already fails
# MIN_PASSWORD_LENGTH (12) on its own, so there's no point carrying
# "password1" and its ilk in this list too. It is not a full breach
# corpus (e.g. a downloaded rockyou/SecLists top-10k) -- swapping in a
# larger list later is a one-line change to the path below, since
# everything else in this module is list-size-agnostic.

from pathlib import Path

_WORDLIST_PATH = Path(__file__).parent / "data" / "common_passwords.txt"


def _load_wordlist() -> frozenset[str]:
    # Loaded once at import and kept as a frozenset -- a plain "in" check
    # against tens of thousands of entries needs to be O(1), not a
    # linear scan on every password submitted.
    with _WORDLIST_PATH.open("r", encoding="utf-8") as handle:
        return frozenset(line.strip() for line in handle if line.strip())


_COMMON_PASSWORDS = _load_wordlist()


def is_commonly_breached(password: str) -> bool:
    # Case-insensitive: "Password123!" and "password123!" are the same
    # weak password to anyone guessing, and a user shouldn't be able to
    # dodge the check by capitalising one letter.
    return password.lower() in _COMMON_PASSWORDS
