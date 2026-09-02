# Settings for the whole backend app, loaded from environment variables.
#
# Using pydantic-settings means we get one place that lists every setting the
# app needs, with sensible local-dev defaults. In Docker, docker-compose.yml
# overrides these via environment variables (see the "environment:" section
# for the "backend" service).

from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Individual Postgres connection pieces (used to build DATABASE_URL below).
    postgres_user: str = "stackfitpro"
    postgres_password: str = "stackfitpro"
    postgres_db: str = "stackfitpro"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    # "prefer" matches libpq's own default (i.e. today's behaviour, which
    # built this URL with no sslmode param at all) -- the bundled
    # container on the test LXC runs with ssl=off, so "require" would
    # simply fail to connect there. A host that terminates TLS on its own
    # bundled Postgres (see docs/PREPROD_DEPLOY.md) sets this to
    # "require". Same reasoning as core/service_db.py's
    # _database_url -- registered *remote* services already default to
    # "require" there; this is the equivalent knob for the one
    # always-local bundled connection this setting builds.
    postgres_sslmode: str = "prefer"

    # CORS: which frontend origin(s) are allowed to call this API.
    # In dev, the React app runs on this origin.
    frontend_origin: str = "http://localhost:5173"

    # Session cookie. `cookie_secure` should be True once the app is only
    # ever served over HTTPS (Phase 9) -- until then, False lets the
    # cookie work over plain http on the test LXC.
    session_cookie_name: str = "stackfitpro_session"
    cookie_secure: bool = False

    # Email sending (password-reset and account-invite links, see
    # app/core/email.py). Two providers, chosen by email_provider:
    #   "smtp" (dev/test default) -- talks to the Mailhog service in
    #     docker-compose.yml, no real credentials needed.
    #   "resend" -- posts to Resend's REST API instead, for
    #     preprod/production (see docs/PREPROD_DEPLOY.md). Only
    #     resend_api_key is read in this mode; the smtp_* settings
    #     below are simply unused.
    email_provider: str = "smtp"
    email_from_address: str = "noreply@stackfitpro.com"

    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False

    # Resend API key (Resend dashboard > API Keys). Required when
    # email_provider="resend" -- validate_email_settings() checks this at
    # startup, not first send. email_from_address must be on a domain
    # that's been verified in Resend's dashboard (see
    # docs/PREPROD_DEPLOY.md's Cloudflare DNS steps) or every send is
    # rejected.
    resend_api_key: str = ""

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
    minio_access_key: str = "stackfitpro"
    minio_secret_key: str = "stackfitpro"
    minio_secure: bool = False
    minio_bucket: str = "stackfitpro-images"

    # Key used to encrypt Postgres/MinIO service credentials before they're
    # stored in the DB (see core/crypto.py) -- a Fernet key, generate one
    # with `Fernet.generate_key()`. Must stay the same across restarts or
    # every stored service's credentials become undecryptable.
    service_credential_key: str = ""

    # Where the backend writes its own log files, and where it reads them
    # back from to serve the admin log viewer (core/logging_config.py,
    # api/logs.py). Must be a Docker volume in any real deployment --
    # anything written to the container's own filesystem is lost on the
    # next rebuild, which is every deploy.
    log_dir: str = "/var/log/stackfitpro"

    # Where Postgres's CSV logs are readable from. Postgres writes them
    # inside its own data directory (the one path it's guaranteed to own),
    # which is mounted read-only into this container -- see
    # docker-compose.yml and api/logs.py.
    postgres_log_dir: str = "/pgdata/log"

    # Shared secret MinIO presents when POSTing its log events to
    # /internal/minio-logs (see api/internal_logs.py). Leaving this blank
    # disables that endpoint entirely rather than leaving it unauthenticated.
    minio_log_webhook_token: str = ""

    # Where scripts/backup_client.py writes per-client snapshots, and
    # where scripts/restore_client.py reads them back from. Must be a
    # Docker volume in any real deployment -- same reasoning as log_dir
    # above -- and see docs/BACKUP_RESTORE.md for what a snapshot
    # contains and why it can't be a plain pg_dump of the whole database.
    backup_dir: str = "/var/backups/stackfitpro"

    @property
    def database_url(self) -> str:
        # quote_plus, not raw interpolation: a generated password
        # containing "@", ":", or "/" would otherwise corrupt the
        # connection string (wrong host, or a silently truncated
        # password) rather than fail loudly. No-op for the test LXC's
        # current alphanumeric credentials.
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?sslmode={self.postgres_sslmode}"
        )


# One shared Settings instance that the rest of the app imports.
settings = Settings()
