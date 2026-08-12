# Tests for the Client tenancy boundary described in CLAUDE.md's "The
# tenancy boundary lives in exactly three helpers" gotcha. Uses the
# db_session fixture (conftest.py) since, unlike the rest of this suite,
# these genuinely need to exercise real queries against real rows --
# root_admin ending up with no access, or a Contributor membership from
# one client not granting anything on another client's project, are both
# properties of the SQL these functions run, not of pure Python logic.

import pytest
from fastapi import HTTPException

from app.api.deps import _user_is_in_project_group, require_client_admin, user_can_view_project
from app.api.reference_data import _get_process_type_or_404
from app.models.client import Client
from app.models.group import CONTRIBUTORS, Group, UserGroupProject
from app.models.minio_service import MinioService
from app.models.postgres_service import PostgresService
from app.models.process_type import ProcessType
from app.models.project import Project
from app.models.user import GlobalRole, User


def _make_services(db_session):
    postgres_service = PostgresService(
        name="pg", host="pg.example", port=5432, database="db", username="u", encrypted_password="x"
    )
    minio_service = MinioService(name="minio", endpoint="minio.example", access_key="k", encrypted_secret_key="x", bucket="b")
    db_session.add_all([postgres_service, minio_service])
    db_session.flush()
    return postgres_service, minio_service


def _make_client(db_session, name, postgres_service, minio_service):
    client = Client(name=name, postgres_service_id=postgres_service.postgres_service_id, minio_service_id=minio_service.minio_service_id)
    db_session.add(client)
    db_session.flush()
    return client


def _make_project(db_session, client, name):
    project = Project(
        client_id=client.client_id,
        project_name=name,
        postgres_service_id=client.postgres_service_id,
        minio_service_id=client.minio_service_id,
    )
    db_session.add(project)
    db_session.flush()
    return project


def _make_user(db_session, client, email, global_role=GlobalRole.standard):
    user = User(
        first_name="Test",
        last_name="User",
        email=email,
        password_hash="x",
        global_role=global_role,
        client_id=client.client_id if client is not None else None,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_user_is_in_project_group_false_for_a_membership_pointing_at_another_clients_project(db_session):
    # A UserGroupProject row that somehow points a client-B user at a
    # client-A project (a stale row, or a bug in whatever created it)
    # must not grant anything -- the tenancy check in
    # _user_is_in_project_group has to reject this before it ever looks
    # at the membership row itself.
    postgres_service, minio_service = _make_services(db_session)
    client_a = _make_client(db_session, "Acme", postgres_service, minio_service)
    client_b = _make_client(db_session, "Globex", postgres_service, minio_service)
    project_a = _make_project(db_session, client_a, "Doors")
    user_b = _make_user(db_session, client_b, "user-b@example.com")

    group = Group(project_id=project_a.project_id, role_name=CONTRIBUTORS)
    db_session.add(group)
    db_session.flush()
    db_session.add(UserGroupProject(user_id=user_b.user_id, group_id=group.group_id, project_id=project_a.project_id))
    db_session.flush()

    assert _user_is_in_project_group(db_session, user_b, project_a.project_id, CONTRIBUTORS) is False


def test_user_is_in_project_group_true_within_the_same_client(db_session):
    postgres_service, minio_service = _make_services(db_session)
    client_a = _make_client(db_session, "Acme", postgres_service, minio_service)
    project_a = _make_project(db_session, client_a, "Doors")
    user_a = _make_user(db_session, client_a, "user-a@example.com")

    group = Group(project_id=project_a.project_id, role_name=CONTRIBUTORS)
    db_session.add(group)
    db_session.flush()
    db_session.add(UserGroupProject(user_id=user_a.user_id, group_id=group.group_id, project_id=project_a.project_id))
    db_session.flush()

    assert _user_is_in_project_group(db_session, user_a, project_a.project_id, CONTRIBUTORS) is True


def test_user_can_view_project_denies_root_admin(db_session):
    # root_admin's client_id is NULL by design (see CLAUDE.md) -- this is
    # the single query that has to turn that NULL into "no access", since
    # api/deps.py's get_project relies on it to 404 a project for
    # root_admin exactly as it would for a stranger.
    postgres_service, minio_service = _make_services(db_session)
    client_a = _make_client(db_session, "Acme", postgres_service, minio_service)
    project_a = _make_project(db_session, client_a, "Doors")
    root_admin = _make_user(db_session, client=None, email="root@example.com", global_role=GlobalRole.root_admin)

    assert user_can_view_project(db_session, root_admin, project_a) is False


def test_require_client_admin_rejects_root_admin():
    # Called directly (not through FastAPI's dependency injection) --
    # it's a plain function once the Depends default is supplied by hand.
    root_admin = User(
        first_name="Root", last_name="Admin", email="root@example.com",
        password_hash="x", global_role=GlobalRole.root_admin, client_id=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        require_client_admin(user=root_admin)
    assert exc_info.value.status_code == 403


def test_get_process_type_or_404_rejects_another_clients_process_type(db_session):
    postgres_service, minio_service = _make_services(db_session)
    client_a = _make_client(db_session, "Acme", postgres_service, minio_service)
    client_b = _make_client(db_session, "Globex", postgres_service, minio_service)
    process_type_a = ProcessType(client_id=client_a.client_id, name="Plastics")
    db_session.add(process_type_a)
    db_session.flush()
    user_b = _make_user(db_session, client_b, "admin-b@example.com", global_role=GlobalRole.client_admin)

    with pytest.raises(HTTPException) as exc_info:
        _get_process_type_or_404(db_session, user_b, process_type_a.process_type_id)
    assert exc_info.value.status_code == 404
