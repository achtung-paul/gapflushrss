# Request rate limiting, used to slow down brute-force attempts against
# the login and password-reset endpoints (see api/auth.py).
#
# The important detail here is how a client is identified. This app always
# runs behind nginx (see nginx/nginx.conf), so every request arrives from
# the nginx container's address -- slowapi's default get_remote_address
# would therefore put *every user in the world into one shared bucket*,
# and a single attacker hitting the limit would lock out everybody at
# once. That would turn a security control into a denial-of-service.
#
# nginx sets X-Real-IP from $remote_addr, overwriting anything the client
# sent, so that header is the real peer address and can't be forged to
# rotate around the limit. We key on it, falling back to the direct peer
# address for the case where the app is reached without nginx in front
# (local development, or a direct container call).

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or get_remote_address(request)


limiter = Limiter(key_func=client_ip)
