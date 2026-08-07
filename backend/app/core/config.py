# Settings for the whole backend app, loaded from environment variables.
#
# Using pydantic-settings means we get one place that lists every setting the
# app needs, with sensible local-dev defaults. In Docker, docker-compose.yml
# overrides these via environment variables (see the "environment:" section
# for the "backend" service).

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Individual Postgres connection pieces (used to build DATABASE_URL below).
    postgres_user: str = "gapflush"
    postgres_password: str = "gapflush"
    postgres_db: str = "gapflush"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # CORS: which frontend origin(s) are allowed to call this API.
    # In dev, the React app runs on this origin.
    frontend_origin: str = "http://localhost:5173"

    # Session cookie. `cookie_secure` should be True once the app is only
    # ever served over HTTPS (Phase 9) -- until then, False lets the
    # cookie work over plain http on the test LXC.
    session_cookie_name: str = "gapflush_session"
    cookie_secure: bool = False

    # SMTP, used for password-reset emails (app/core/email.py). Defaults
    # match the Mailhog dev service in docker-compose.yml.
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_from_address: str = "noreply@gapflushrss.local"

    # First-run bootstrap: if no root_admin user exists yet, one is
    # created from these on startup (see app/main.py). Only takes effect
    # when all four are set.
    root_admin_first_name: str = ""
    root_admin_last_name: str = ""
    root_admin_email: str = ""
    root_admin_password: str = ""

    # MinIO (S3-compatible) object storage. Only read once, by the
    # one-time migration that seeds the "Default" MinioService row (see
    # alembic/versions/fe5a0c40a1ce_multi_service_postgres_minio.py) --
    # after that, every MinIO connection goes through a MinioService row
    # instead (app/core/service_storage.py). Defaults match the "minio"
    # service in docker-compose.yml.
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "gapflush"
    minio_secret_key: str = "gapflush"
    minio_secure: bool = False
    minio_bucket: str = "gapflushrss-images"

    # Key used to encrypt Postgres/MinIO service credentials before they're
    # stored in the DB (see core/crypto.py) -- a Fernet key, generate one
    # with `Fernet.generate_key()`. Must stay the same across restarts or
    # every stored service's credentials become undecryptable.
    service_credential_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# One shared Settings instance that the rest of the app imports.
settings = Settings()
