# Root admin's management of Clients (SaaS tenants) -- the one place
# root admin creates a client's sandbox and its first admin, and the
# non-destructive lever (deactivate) for a lapsed subscription.
#
# Root admin's view of a client is deliberately thin: name, which
# services it sits on, whether it's active, how many projects it has,
# and its client_admin accounts. Never project names, never ordinary
# user accounts, never any analysis data -- per the brief, root admin
# configures infrastructure and nothing else. Every query below is
# written to return only those fields; nothing here can reach a project
# or a non-admin user. See CLAUDE.md's tenancy-boundary gotcha.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_root_admin
from app.api.projects import purge_project_data
from app.core import service_db, service_provisioning, service_storage
from app.core.invites import build_invited_user, send_account_invite
from app.core.security import force_password_reset
from app.core.statistical_model_defaults import default_statistical_model_rows
from app.db.session import get_db
from app.models.client import Client
from app.models.login_challenge import LoginChallenge
from app.models.minio_server import MinioServer
from app.models.minio_service import MinioService
from app.models.password_reset_token import PasswordResetToken
from app.models.postgres_server import PostgresServer
from app.models.postgres_service import PostgresService
from app.models.process_type import ProcessType
from app.models.project import Project
from app.models.statistical_model_setting import StatisticalModelSetting
from app.models.user import GlobalRole, User
from app.models.user_session import UserSession
from app.models.user_totp import UserTotp
from app.schemas.client import ClientAdminCreate, ClientAdminOut, ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/admin/clients", tags=["admin"])


def _get_client_or_404(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _get_client_admin_or_404(db: Session, client_id: int, user_id: int) -> User:
    # The global_role filter is what stops root admin reaching an
    # ordinary client employee through this route -- requirement 4 of
    # the brief ("root_admin ... does not have visibility of customer
    # employees") comes down to exactly this one WHERE clause.
    user = db.get(User, user_id)
    if user is None or user.client_id != client_id or user.global_role != GlobalRole.client_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client admin not found")
    return user


def _client_out(db: Session, client: Client) -> ClientOut:
    project_count = db.query(func.count(Project.project_id)).filter(Project.client_id == client.client_id).scalar()
    return ClientOut(
        client_id=client.client_id,
        name=client.name,
        postgres_service_id=client.postgres_service_id,
        minio_service_id=client.minio_service_id,
        is_active=client.is_active,
        project_count=project_count,
    )


def _kill_client_sessions(db: Session, client_id: int) -> None:
    # Shared by update_client's deactivate path and delete_client below --
    # both need every open session for this client's users gone so
    # nobody keeps working (or writing) against data that's about to be
    # frozen or purged.
    user_ids = [row.user_id for row in db.query(User.user_id).filter(User.client_id == client_id).all()]
    if user_ids:
        db.query(UserSession).filter(UserSession.user_id.in_(user_ids)).delete(synchronize_session=False)


def _seed_default_process_type(db: Session, client_id: int) -> None:
    # Was core/bootstrap.py's create_default_process_types_if_needed,
    # which seeded one global "Plastics" at app startup. Process types
    # are per-client now (models/process_type.py), so seeding happens
    # here instead: a new client starts with something in the list
    # rather than an empty tolerance-matrix screen. v1 scope is plastics
    # only, per the brief.
    db.add(ProcessType(client_id=client_id, name="Plastics"))


def _seed_default_statistical_model_settings(db: Session, client_id: int) -> None:
    # StatisticalModelSetting assumes exactly 5 rows (sigma 1-5) always
    # exist per client -- see models/statistical_model_setting.py. This
    # is the only place a new client gets them; a pre-existing client got
    # theirs from this feature's own migration's backfill (same defaults,
    # see core/statistical_model_defaults.py).
    for row in default_statistical_model_rows(client_id):
        db.add(StatisticalModelSetting(**row))


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), _: User = Depends(require_root_admin)):
    clients = db.query(Client).order_by(Client.name).all()
    return [_client_out(db, client) for client in clients]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    body: ClientCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(Client).filter(Client.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client name already exists")

    email_taken = db.query(User).filter(User.email == body.admin_email).first()
    if email_taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    # Every check in this block has to pass *before* anything below can
    # provision real infrastructure. CREATE DATABASE / mc admin commands
    # commit on the external server the instant they run, independent of
    # this request's own db transaction -- a later db.rollback() can't
    # undo them the way it undoes an ordinary INSERT, so every avoidable
    # failure needs to happen first. ClientCreate's own validator already
    # guarantees exactly one of each pair (service id / server id) is set.
    postgres_server: PostgresServer | None = None
    if body.postgres_service_id is not None:
        # A project can never point at a service that isn't ready -- same
        # guard api/projects.py's create_project used to make directly,
        # now made once here since a client's projects all inherit its
        # services.
        postgres_service = db.get(PostgresService, body.postgres_service_id)
        if postgres_service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postgres service not found")
        if service_db.check_status(postgres_service) != "initialized":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Postgres service isn't initialized yet")
        # Isolation is by dedicated infrastructure -- a service already
        # assigned to another client can't be handed to a second one, or
        # their Commodity-and-below data would end up colocated on one
        # physical database with only application code (not a real
        # boundary) telling their rows apart. See CLAUDE.md.
        postgres_in_use = db.query(Client).filter(Client.postgres_service_id == body.postgres_service_id).first()
        if postgres_in_use is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That Postgres service is already assigned to another client",
            )
    else:
        postgres_server = db.get(PostgresServer, body.postgres_server_id)
        if postgres_server is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postgres server not found")

    minio_server: MinioServer | None = None
    if body.minio_service_id is not None:
        minio_service = db.get(MinioService, body.minio_service_id)
        if minio_service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MinIO service not found")
        if service_storage.check_status(minio_service) != "initialized":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MinIO service isn't initialized yet")
        minio_in_use = db.query(Client).filter(Client.minio_service_id == body.minio_service_id).first()
        if minio_in_use is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That MinIO service is already assigned to another client",
            )
    else:
        minio_server = db.get(MinioServer, body.minio_server_id)
        if minio_server is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MinIO server not found")

    # Postgres first, MinIO second -- deliberate order, since the
    # cleanup below only runs "undo Postgres if MinIO then fails", not
    # the other way around.
    if postgres_server is not None:
        try:
            postgres_service = service_provisioning.provision_postgres_service(db, postgres_server, body.name)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not provision a dedicated Postgres database: {error}",
            )

    if minio_server is not None:
        try:
            minio_service = service_provisioning.provision_minio_service(db, minio_server, body.name)
        except Exception as error:
            if postgres_server is not None:
                service_provisioning.deprovision_postgres_service(postgres_server, postgres_service)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not provision a dedicated MinIO bucket: {error}",
            )

    client = Client(
        name=body.name,
        postgres_service_id=postgres_service.postgres_service_id,
        minio_service_id=minio_service.minio_service_id,
    )
    db.add(client)
    db.flush()  # assigns client.client_id without ending the transaction

    # A client can never exist without at least one admin (requirement 2
    # of the brief) -- created in the same transaction as the client
    # itself, so that's true by construction, not by convention. No
    # password -- the admin account starts unusable until the invite
    # link below is used (see core/invites.py).
    admin = build_invited_user(
        first_name=body.admin_first_name,
        last_name=body.admin_last_name,
        email=body.admin_email,
        global_role=GlobalRole.client_admin,
        client_id=client.client_id,
    )
    db.add(admin)
    _seed_default_process_type(db, client.client_id)
    _seed_default_statistical_model_settings(db, client.client_id)

    db.commit()
    db.refresh(client)
    db.refresh(admin)

    try:
        send_account_invite(db, admin)
    except OSError as error:
        # The client and its admin account both already exist and are
        # committed -- same recovery path as every other invite-issuing
        # route: root admin uses resend-invite (below) once mail is
        # working again, rather than the whole client creation failing.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Client created, but the admin's invite email failed to send: {error}",
        )
    return _client_out(db, client)


@router.get("/{client_id}/admins", response_model=list[ClientAdminOut])
def list_client_admins(
    client_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    _get_client_or_404(db, client_id)
    admins = (
        db.query(User)
        .filter(User.client_id == client_id, User.global_role == GlobalRole.client_admin)
        .order_by(User.last_name, User.first_name)
        .all()
    )
    return admins


@router.post("/{client_id}/admins", response_model=ClientAdminOut, status_code=status.HTTP_201_CREATED)
def add_client_admin(
    client_id: int,
    body: ClientAdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    # The recovery path when a client's only admin leaves -- root admin
    # can register a replacement without being able to see anything else
    # about the client.
    _get_client_or_404(db, client_id)

    existing = db.query(User).filter(User.email == body.email).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    admin = build_invited_user(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        global_role=GlobalRole.client_admin,
        client_id=client_id,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    try:
        send_account_invite(db, admin)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User created, but the invite email failed to send: {error}",
        )
    return admin


@router.post("/{client_id}/admins/{user_id}/force-password-reset", status_code=status.HTTP_204_NO_CONTENT)
def force_client_admin_password_reset(
    client_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    admin = _get_client_admin_or_404(db, client_id, user_id)
    force_password_reset(db, admin)
    db.commit()


@router.post("/{client_id}/admins/{user_id}/resend-invite", status_code=status.HTTP_204_NO_CONTENT)
def resend_client_admin_invite(
    client_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    admin = _get_client_admin_or_404(db, client_id, user_id)
    try:
        send_account_invite(db, admin)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to send invite email: {error}"
        )


@router.post("/{client_id}/admins/{user_id}/reset-2fa", status_code=status.HTTP_204_NO_CONTENT)
def reset_client_admin_2fa(
    client_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    """Recovery path for a client admin who's lost their authenticator
    device -- mirrors api/client_admin.py's reset_client_user_2fa. Root
    admin can reach this one client_admin account (via
    _get_client_admin_or_404) without gaining any other visibility into
    the client -- same boundary as force-password-reset above.
    """
    admin = _get_client_admin_or_404(db, client_id, user_id)
    db.query(UserTotp).filter(UserTotp.user_id == admin.user_id).delete()
    db.query(LoginChallenge).filter(LoginChallenge.user_id == admin.user_id).delete()
    db.query(UserSession).filter(UserSession.user_id == admin.user_id).delete()
    db.commit()


@router.put("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    body: ClientUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    client = _get_client_or_404(db, client_id)

    existing = db.query(Client).filter(Client.name == body.name).first()
    if existing is not None and existing.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client name already exists")

    was_active = client.is_active
    client.name = body.name
    client.is_active = body.is_active

    # Deactivating doesn't just block future logins (api/auth.py) -- it
    # also kills every session already open for this client's users, so
    # deactivation is a real security action, not just a billing nudge
    # that takes up to SESSION_LIFETIME (7 days) to actually bite.
    if was_active and not body.is_active:
        _kill_client_sessions(db, client_id)

    db.commit()
    db.refresh(client)
    return _client_out(db, client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    """Permanently purge a client: every project's data, every user, the
    client itself -- after taking a full snapshot first.

    Root admin can't see this client's data, so the snapshot is what
    makes "we can restore from backup" true by construction rather than
    by hoping someone remembered to run one (see scripts/backup_client.py,
    docs/BACKUP_RESTORE.md). If the snapshot fails for any reason, the
    request fails and nothing is deleted -- a failed backup must never
    become a silent data loss.
    """
    client = _get_client_or_404(db, client_id)
    # Captured now, not read off `client` after it's deleted below --
    # SQLAlchemy expires a deleted object on commit, so `client.<column>`
    # would try to re-SELECT a row that no longer exists.
    postgres_service_id = client.postgres_service_id
    minio_service_id = client.minio_service_id

    # 1. Freeze the client first, so nothing writes to its data while
    # the snapshot below is being taken.
    client.is_active = False
    _kill_client_sessions(db, client_id)
    db.commit()

    # 2. Snapshot everything. Imported here, not at module load, since
    # this is the only route that needs it -- every other admin_clients
    # route has nothing to do with scripts/.
    from scripts.backup_client import main as backup_client_snapshot

    try:
        backup_client_snapshot(client_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Snapshot failed -- nothing was deleted. {error}",
        )

    # 3. Purge every project's data (MinIO objects, then Commodity rows,
    # then the Project row itself -- see purge_project_data and
    # api/projects.py's delete_project, which this is the multi-project
    # form of). Each project's own postgres_service_id/minio_service_id
    # is used, not the client's directly -- they're copied at project
    # creation and are the same services today, but resolving per-project
    # keeps this correct even if that ever changes.
    projects = db.query(Project).filter(Project.client_id == client_id).all()
    for project in projects:
        postgres_service = db.get(PostgresService, project.postgres_service_id)
        minio_service = db.get(MinioService, project.minio_service_id)
        project_db = service_db.get_session(postgres_service)
        try:
            purge_project_data(project_db, minio_service, project.project_id)
        finally:
            project_db.close()
        # Groups (and their UserGroupProject rows) cascade from this
        # delete -- see models/group.py's ondelete="CASCADE" FK.
        db.delete(project)
    db.commit()

    # 4. Delete the client's users. None of their FKs cascade (same
    # "delete it by hand first" pattern as api/admin.py's delete_user),
    # and UserGroupProject is already gone via the project deletes above.
    users = db.query(User).filter(User.client_id == client_id).all()
    for user in users:
        db.query(UserSession).filter(UserSession.user_id == user.user_id).delete()
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.user_id).delete()
        db.query(UserTotp).filter(UserTotp.user_id == user.user_id).delete()
        db.query(LoginChallenge).filter(LoginChallenge.user_id == user.user_id).delete()
        db.delete(user)
    db.commit()

    # 5. The client row itself -- process_types (and the whole tolerance
    # matrix cascading from them) go with it automatically
    # (ondelete="CASCADE" on process_types.client_id).
    db.delete(client)
    db.commit()

    # 6. Drop cached connections for services that might now be free --
    # harmless if another client is still using either one, since
    # get_session/get_client just reconnect and re-cache on next use.
    postgres_service = db.get(PostgresService, postgres_service_id)
    minio_service = db.get(MinioService, minio_service_id)
    if postgres_service is not None:
        service_db.evict(postgres_service)
    if minio_service is not None:
        service_storage.evict(minio_service)
