# Request/response shapes for /admin/clients (root admin) and the parts
# of /client-admin that report a client's own identity back to itself.

from pydantic import BaseModel, EmailStr, ConfigDict, field_validator, model_validator


class ClientCreate(BaseModel):
    name: str
    # Exactly one of (postgres_service_id) or (postgres_server_id) must be
    # given, and likewise for the MinIO pair -- either pick an existing,
    # already-dedicated service, or hand over a registered server to
    # auto-provision a brand-new one from (see
    # core/service_provisioning.py). Enforced below rather than as two
    # separate required fields, so the request shape stays one schema
    # instead of a branching union.
    postgres_service_id: int | None = None
    postgres_server_id: int | None = None
    minio_service_id: int | None = None
    minio_server_id: int | None = None
    # A client can never exist without at least one admin (requirement 2
    # of the brief) -- so the first one is created in the same request,
    # the same transaction, as the client itself. No admin_password --
    # the admin account is created with an unusable password hash and an
    # emailed invite link (see api/admin_clients.py's create_client,
    # core/security.py's hash_unusable_password).
    admin_first_name: str
    admin_last_name: str
    admin_email: EmailStr

    @model_validator(mode="after")
    def exactly_one_postgres_and_one_minio_source(self) -> "ClientCreate":
        if (self.postgres_service_id is None) == (self.postgres_server_id is None):
            raise ValueError("Provide exactly one of postgres_service_id or postgres_server_id")
        if (self.minio_service_id is None) == (self.minio_server_id is None):
            raise ValueError("Provide exactly one of minio_service_id or minio_server_id")
        return self


class ClientUpdate(BaseModel):
    name: str
    is_active: bool


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_id: int
    name: str
    postgres_service_id: int
    minio_service_id: int
    is_active: bool
    # Built by hand in api/admin_clients.py (a COUNT, not a relationship)
    # -- root admin is deliberately told how many projects a client has
    # and nothing else about them: never a name, never an id. See
    # CLAUDE.md's tenancy-boundary gotcha.
    project_count: int


class ClientAdminCreate(BaseModel):
    # No password field -- same invite-by-email flow as ClientCreate
    # above (api/admin_clients.py's add_client_admin).
    first_name: str
    last_name: str
    email: EmailStr

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ClientAdminOut(BaseModel):
    # Only ever returned from a route filtered to global_role ==
    # client_admin -- see api/admin_clients.py's list_client_admins. A
    # root admin must never be able to reach an ordinary client user
    # through this shape.
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    first_name: str
    last_name: str
    email: EmailStr
