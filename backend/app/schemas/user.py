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


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    global_role: GlobalRole = GlobalRole.standard

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class UserUpdate(BaseModel):
    # Same shape as UserCreate minus password -- password changes stay
    # on the existing email-based reset-token flow (api/auth.py), not
    # this endpoint. Added alongside the username -> first/last name
    # migration so a user backfilled with a placeholder surname (see
    # that migration) can actually be fixed afterward.
    first_name: str
    last_name: str
    email: EmailStr
    global_role: GlobalRole

    @field_validator("first_name", "last_name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class UserListOut(BaseModel):
    # A page of users plus the total count matching the search, so the
    # frontend can render "page X of Y" / breadcrumb links without a
    # second request.
    items: list[UserOut]
    total: int
