from typing import Literal

from pydantic import BaseModel, EmailStr

# Matches the three group kinds every project gets (app/models/group.py).
GroupRole = Literal["Managers", "Contributors", "Viewers"]


class GroupMembershipCreate(BaseModel):
    user_id: int
    group_role: GroupRole


class GroupMemberOut(BaseModel):
    # Built by hand in api/admin.py, not model_validate'd off a row --
    # username/email come from the joined User, group_role is derived
    # from the joined Group's name (see _group_name in api/projects.py).
    user_id: int
    username: str
    email: EmailStr
    group_role: GroupRole
