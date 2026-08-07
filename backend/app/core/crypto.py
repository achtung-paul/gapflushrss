# Encrypts Postgres/MinIO service credentials before they're stored in
# the database (see models/postgres_service.py, models/minio_service.py).
# Uses Fernet (symmetric, from the `cryptography` package) rather than
# hashing -- unlike a user password, we need to get the plaintext back
# out again to actually connect to the service.

from cryptography.fernet import Fernet

from app.core.config import settings

# Fails fast and loudly on a bad/missing key rather than silently
# falling back to something insecure -- an app that can't decrypt its
# stored service credentials can't function anyway, so there's no
# graceful degradation worth building.
_fernet = Fernet(settings.service_credential_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
