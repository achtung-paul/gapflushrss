from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import GlobalRole


class UserOut(BaseModel):
    # Lets pydantic read these fields straight off a SQLAlchemy User
    # object (model_config), instead of only off a dict.
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    email: EmailStr
    global_role: GlobalRole


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    global_role: GlobalRole = GlobalRole.standard


class UserListOut(BaseModel):
    # A page of users plus the total count matching the search, so the
    # frontend can render "page X of Y" / breadcrumb links without a
    # second request.
    items: list[UserOut]
    total: int
