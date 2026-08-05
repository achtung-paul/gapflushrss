from typing import Literal

from pydantic import BaseModel

# Matches the three group kinds every project gets (app/models/group.py).
GroupRole = Literal["Managers", "Contributors", "Viewers"]


class GroupMembershipCreate(BaseModel):
    user_id: int
    group_role: GroupRole
