# Auto-provisions a brand-new, dedicated PostgresService/MinioService for
# a client, rather than requiring root admin to have pre-registered one
# by hand (api/postgres_services.py / api/minio_services.py). Used by
# api/admin_clients.py's create_client as an alternative to picking an
# existing service.
#
# Both halves create least-privilege, client-specific credentials rather
# than reusing the server-level admin/root credentials for ordinary data
# access -- a shared superuser-ish credential used for every client's
# everyday connections would be exactly the kind of gap a TISAX-style
# review flags. The server-level credentials (PostgresServer.admin_password,
# MinioServer.root_secret_key) never leave this module.

import json
import logging
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.orm import Session

from app.core import service_db
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.minio_server import MinioServer
from app.models.minio_service import MinioService
from app.models.postgres_server import PostgresServer
from app.models.postgres_service import PostgresService

logger = logging.getLogger(__name__)

# How many "<slug>", "<slug>_2", "<slug>_3", ... attempts to make before
# giving up on a name collision -- a client name colliding with an
# existing database/role/bucket three times over is almost certainly a
# real naming clash worth surfacing, not something to loop on forever.
MAX_NAME_ATTEMPTS = 5


def _postgres_slug(client_name: str) -> str:
    # Postgres identifiers: lowercase (unquoted identifiers fold to
    # lowercase anyway, so making that explicit here avoids a
    # generated name silently meaning something different from what's
    # displayed), letters/digits/underscores only, must not start with a
    # digit, kept well under the 63-byte limit so a numeric retry suffix
    # (see MAX_NAME_ATTEMPTS) always fits.
    slug = re.sub(r"[^a-z0-9_]", "_", client_name.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug) or "client"
    if slug[0].isdigit():
        slug = f"c_{slug}"
    return slug[:40]


def _minio_bucket_slug(client_name: str) -> str:
    # S3/MinIO bucket naming rules: lowercase letters, digits, hyphens
    # only (no underscores), 3-63 characters, must start and end with a
    # letter or digit.
    slug = re.sub(r"[^a-z0-9-]", "-", client_name.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug) or "client"
    slug = slug[:40].strip("-") or "client"
    if len(slug) < 3:
        slug = f"{slug}-bucket"
    return slug


def _generate_password() -> str:
    # URL-safe so it never needs escaping when it ends up in a
    # connection string or an mc command -- same generator already used
    # for session/reset tokens (core/security.py).
    return secrets.token_urlsafe(24)


def provision_postgres_service(db: Session, server: PostgresServer, client_name: str) -> PostgresService:
    """Create a dedicated database + login role on `server` for a new client.

    Connects to the server's `postgres` maintenance database using the
    server's admin credentials, issues CREATE ROLE + CREATE DATABASE for
    a brand-new role/database pair, then registers a PostgresService row
    using *that* role's credentials -- never the admin credentials
    themselves -- for all of this client's ordinary connections.
    """
    admin_password = decrypt_secret(server.encrypted_admin_password)
    base_slug = _postgres_slug(client_name)

    last_error: Exception | None = None
    for attempt in range(1, MAX_NAME_ATTEMPTS + 1):
        slug = base_slug if attempt == 1 else f"{base_slug}_{attempt}"
        role_name = f"gf_{slug}"
        database_name = f"gapflush_{slug}"

        # Postgres won't run CREATE DATABASE inside a transaction block,
        # so this connection has to be in autocommit mode -- there's no
        # single transaction to roll back if something after the role
        # creation fails, which is exactly why each step below checks for
        # (and cleans up after) a partial failure by hand.
        connection = psycopg2.connect(
            host=server.host,
            port=server.port,
            dbname="postgres",
            user=server.admin_username,
            password=admin_password,
            connect_timeout=service_db.CONNECT_TIMEOUT_SECONDS,
        )
        connection.autocommit = True
        role_password = _generate_password()
        # Tracks whether *this attempt* actually created the role, so the
        # except block below only ever drops a role it just made itself
        # -- not the pre-existing role a collision was reported against.
        # An earlier version dropped `role_name` unconditionally on any
        # duplicate error, which meant a role-name collision (CREATE ROLE
        # itself failing, because a *different, already-in-use* client
        # already owns that name) tried to drop that other client's role
        # -- caught by Postgres refusing ("cannot be dropped because some
        # objects depend on it", i.e. it owns a real database), not by
        # code review. Only a CREATE DATABASE collision *after* a
        # successful CREATE ROLE is safe to roll back this way, since
        # that role was just created in this same attempt and owns
        # nothing yet.
        role_created_this_attempt = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role_name)),
                    (role_password,),
                )
                role_created_this_attempt = True
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(database_name), sql.Identifier(role_name)
                    )
                )
            break
        except (psycopg2.errors.DuplicateObject, psycopg2.errors.DuplicateDatabase) as error:
            # Name collision -- the role or database already exists
            # (most likely from a previous client). Try the next suffix.
            last_error = error
            if role_created_this_attempt:
                with connection.cursor() as cursor:
                    cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role_name)))
            continue
        finally:
            connection.close()
    else:
        raise RuntimeError(
            f"Could not find a free database/role name for {client_name!r} after "
            f"{MAX_NAME_ATTEMPTS} attempts (last error: {last_error})"
        )

    service = PostgresService(
        name=f"{server.name}: {database_name}",
        host=server.host,
        port=server.port,
        database=database_name,
        username=role_name,
        encrypted_password=encrypt_secret(role_password),
        provisioned_from_server_id=server.postgres_server_id,
    )
    db.add(service)
    db.flush()  # assigns service.postgres_service_id

    # Bring the new (empty) database up to the project schema's current
    # head -- the same call the admin "Initialize" button makes for a
    # manually-registered service (core/service_db.py).
    service_db.initialize_schema(service)
    return service


def deprovision_postgres_service(server: PostgresServer, service: PostgresService) -> None:
    """Best-effort cleanup for a database+role this module just created.

    Used only when a *later* step in the same client-creation request
    fails (api/admin_clients.py's create_client) -- CREATE DATABASE/CREATE
    ROLE already committed on the external server the moment they ran,
    independent of this app's own database transaction, so a plain
    db.rollback() can't undo them. Never raises: the caller is already
    handling the original failure, and an exception from cleanup here
    would mask it. A failure is logged instead, and the orphaned database
    is left for a human to clean up by hand.
    """
    try:
        admin_password = decrypt_secret(server.encrypted_admin_password)
        connection = psycopg2.connect(
            host=server.host,
            port=server.port,
            dbname="postgres",
            user=server.admin_username,
            password=admin_password,
            connect_timeout=service_db.CONNECT_TIMEOUT_SECONDS,
        )
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(service.database)))
            cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(service.username)))
        connection.close()
    except Exception:
        logger.warning(
            "Failed to clean up provisioned Postgres database %r after a later failure -- "
            "remove it by hand.",
            service.database,
            exc_info=True,
        )


def _run_mc(args: list[str], config_dir: Path) -> subprocess.CompletedProcess:
    # --config-dir isolates this call's alias/credentials to a throwaway
    # directory instead of mc's default ~/.mc -- concurrent provisioning
    # calls (or any other mc usage on this host) never share state, and
    # the whole directory is removed once provisioning finishes, so no
    # root credential is left sitting on disk afterward.
    return subprocess.run(
        ["mc", "--config-dir", str(config_dir), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )


def _bucket_scoped_policy(bucket: str) -> dict:
    # Full S3 access, but only within this one bucket -- matches what a
    # manually-registered MinioService's credentials are already trusted
    # to do today (upload/download/delete/list/create), just scoped down
    # from "the whole server" (the root credential) to "this one bucket".
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:*"],
                "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }


def provision_minio_service(db: Session, server: MinioServer, client_name: str) -> MinioService:
    """Create a dedicated bucket + bucket-scoped IAM user on `server`.

    Shells out to the `mc` CLI (no admin/IAM operations exist in the
    `minio` Python SDK already used elsewhere in this app -- see
    core/service_storage.py, which is a plain S3-protocol client) using
    the server's root credentials, then registers a MinioService row
    using a freshly generated, bucket-scoped access key -- never the
    root credentials themselves.
    """
    root_secret = decrypt_secret(server.encrypted_root_secret_key)
    base_slug = _minio_bucket_slug(client_name)
    scheme = "https" if server.secure else "http"

    with tempfile.TemporaryDirectory(prefix="gapflush-mc-") as tmp:
        config_dir = Path(tmp)
        alias = "target"
        _run_mc(
            ["alias", "set", alias, f"{scheme}://{server.endpoint}", server.root_access_key, root_secret],
            config_dir,
        )

        bucket_name = None
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(1, MAX_NAME_ATTEMPTS + 1):
            candidate = base_slug if attempt == 1 else f"{base_slug}-{attempt}"
            try:
                _run_mc(["mb", f"{alias}/{candidate}"], config_dir)
                bucket_name = candidate
                break
            except subprocess.CalledProcessError as error:
                last_error = error
                continue
        if bucket_name is None:
            raise RuntimeError(
                f"Could not find a free bucket name for {client_name!r} after "
                f"{MAX_NAME_ATTEMPTS} attempts (last error: {last_error.stderr if last_error else None})"
            )

        access_key = secrets.token_hex(10)
        secret_key = _generate_password()
        _run_mc(["admin", "user", "add", alias, access_key, secret_key], config_dir)

        policy_name = f"gf-{bucket_name}"
        policy_path = config_dir / "policy.json"
        policy_path.write_text(json.dumps(_bucket_scoped_policy(bucket_name)))
        _run_mc(["admin", "policy", "create", alias, policy_name, str(policy_path)], config_dir)
        _run_mc(["admin", "policy", "attach", alias, policy_name, "--user", access_key], config_dir)

    service = MinioService(
        name=f"{server.name}: {bucket_name}",
        endpoint=server.endpoint,
        access_key=access_key,
        encrypted_secret_key=encrypt_secret(secret_key),
        secure=server.secure,
        bucket=bucket_name,
        provisioned_from_server_id=server.minio_server_id,
    )
    db.add(service)
    db.flush()  # assigns service.minio_service_id
    return service
