from typing import Literal

from pydantic import BaseModel, EmailStr

# Matches the three group kinds every project gets (app/models/group.py).
GroupRole = Literal["Managers", "Contributors", "Viewers"]


class GroupMembershipCreate(BaseModel):
    user_id: int
    group_role: GroupRole


class GroupMemberOut(BaseModel):
    # Built by hand in api/admin.py, not model_validate'd off a row --
    # first_name/last_name/email come from the joined User, group_role is
    # the joined Group's role_name column directly.
    user_id: int
    first_name: str
    last_name: str
    email: EmailStr
    group_role: GroupRole
