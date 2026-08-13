from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models.user import GlobalRole


class UserOut(BaseModel):
    # Lets pydantic read these fields straight off a SQLAlchemy User
    # object (model_config), instead of only off a dict.
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    first_name: str
    last_name: str
    email: EmailStr
    global_role: GlobalRole


class CurrentUserOut(UserOut):
    # Returned by both /auth/login and /auth/me -- see api/auth.py's
    # _current_user_out, which is the one place that builds this, so the
    # two routes can never drift into returning different shapes (the
    # frontend's AuthContext hydrates from one and refreshes from the
    # other and assumes they match).
    client_id: int | None
    client_name: str | None


def _name_must_not_be_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class RootAdminCreate(BaseModel):
    # No global_role field at all -- every account created through
    # /admin/root-admins is a root_admin by definition, so there's
    # nothing to pick and nothing that could be picked wrong.
    #
    # No password field either -- the account starts with an unusable
    # password hash and an emailed invite link to set one (see
    # api/admin.py's create_root_admin, core/security.py's
    # hash_unusable_password). Nobody but the new user ever knows their
    # own password.
    first_name: str
    last_name: str
    email: EmailStr

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        return _name_must_not_be_blank(value)


class RootAdminUpdate(BaseModel):
    # Password isn't editable here -- that stays on the existing
    # email-based reset-token flow (api/auth.py).
    first_name: str
    last_name: str
    email: EmailStr

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        return _name_must_not_be_blank(value)


class UserListOut(BaseModel):
    # A page of users plus the total count matching the search, so the
    # frontend can render "page X of Y" / breadcrumb links without a
    # second request.
    items: list[UserOut]
    total: int


# The two roles a client admin is allowed to hand out within their own
# sandbox. Deliberately a Literal, not the full GlobalRole enum -- a
# client admin sending "root_admin" here is rejected by Pydantic with a
# 422 before any code runs, rather than needing a runtime check.
ClientUserRole = Literal["standard", "client_admin"]


class ClientUserCreate(BaseModel):
    # No password field -- see RootAdminCreate's comment above; the same
    # invite-by-email flow applies here (api/client_admin.py's
    # create_client_user).
    first_name: str
    last_name: str
    email: EmailStr
    global_role: ClientUserRole = "standard"

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        return _name_must_not_be_blank(value)


class ClientUserUpdate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    global_role: ClientUserRole

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        return _name_must_not_be_blank(value)
