# Request/response shapes for /admin/clients (root admin) and the parts
# of /client-admin that report a client's own identity back to itself.

from pydantic import BaseModel, EmailStr, ConfigDict, field_validator

from app.core.security import validate_password_strength


class ClientCreate(BaseModel):
    name: str
    postgres_service_id: int
    minio_service_id: int
    # A client can never exist without at least one admin (requirement 2
    # of the brief) -- so the first one is created in the same request,
    # the same transaction, as the client itself.
    admin_first_name: str
    admin_last_name: str
    admin_email: EmailStr
    admin_password: str

    @field_validator("admin_password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        return validate_password_strength(value)


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
    first_name: str
    last_name: str
    email: EmailStr
    password: str

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        return validate_password_strength(value)


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
