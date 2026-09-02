# TOTP (Time-based One-Time Password, RFC 6238) generation and
# verification for 2FA login (see api/auth.py's login() gate,
# models/user_totp.py, models/login_challenge.py).
#
# Uses pyotp for the actual HMAC-SHA1 time-step algorithm -- hand-rolling
# that math is exactly the kind of "looks right, subtly isn't" code a
# security feature shouldn't carry. This module adds the two things
# pyotp doesn't provide on its own: a QR code image for enrollment and
# step-based replay protection.

import base64
import io
import time

import pyotp
import qrcode

# 30 seconds is the RFC 6238 default and what every authenticator app
# (Google Authenticator, Authy, 1Password, ...) assumes when it reads the
# otpauth:// URI -- changing it would produce codes those apps can't
# generate correctly.
TOTP_STEP_SECONDS = 30

# Accept a code from one step before or after the current one, to absorb
# ordinary clock drift between the server and the user's phone. Wider
# than this starts trading security for convenience.
VALID_WINDOW = 1

ISSUER = "StackFit Pro"


def generate_secret() -> str:
    """A fresh base32 TOTP secret -- pyotp's own generator (20 random bytes)."""
    return pyotp.random_base32()


def otpauth_uri(secret: str, email: str) -> str:
    """The otpauth:// URI an authenticator app reads out of the QR code."""
    return pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS).provisioning_uri(
        name=email, issuer_name=ISSUER
    )


def qr_code_data_uri(uri: str) -> str:
    """Render the enrollment URI as a PNG data: URI the frontend can drop
    straight into an <img src>.

    A PNG via <img>, not an inline SVG string: CLAUDE.md's
    dangerouslySetInnerHTML gotcha reserves that escape hatch for
    exactly one value in the whole app (the sanitised AnalysisEntry.notes
    field) specifically so there's only ever one HTML injection point to
    reason about -- a QR code is server-generated and not
    attacker-controlled, but adding a second dangerouslySetInnerHTML call
    for convenience is still the wrong tradeoff. qrcode's default image
    factory renders through Pillow, already a dependency
    (core/excel_export.py), so this adds nothing new.
    """
    img = qrcode.make(uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def current_step(for_time: float | None = None) -> int:
    """The RFC 6238 time step "now" falls in (or an arbitrary time, for tests)."""
    ts = time.time() if for_time is None else for_time
    return int(ts // TOTP_STEP_SECONDS)


def verify_code(secret: str, code: str, last_used_step: int | None) -> int | None:
    """Check a 6-digit code against the secret, allowing one step of
    clock drift either way, and refusing to accept a step that's already
    been consumed once.

    The replay check matters because a TOTP code stays valid for its
    whole ~30-second window -- without last_used_step, someone who
    shoulder-surfs or intercepts a code (e.g. over a compromised network
    before TLS is enforced -- see CLAUDE.md's production checklist) could
    reuse it a second time within that window.

    Returns the step number that matched (the caller stores it as the
    new last_used_step), or None if the code didn't match any candidate
    step or matched one already used.
    """
    code = code.strip()
    totp = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS)
    now = time.time()
    for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):
        step = current_step(now) + offset
        if last_used_step is not None and step <= last_used_step:
            continue
        candidate_time = step * TOTP_STEP_SECONDS
        if totp.at(candidate_time) == code:
            return step
    return None
