# Request/response shapes for the system-wide 2FA toggle
# (api/security_settings.py, models/security_setting.py).

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SecuritySettingUpdate(BaseModel):
    require_2fa: bool


class SecuritySettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    require_2fa: bool
    updated_at: datetime
    updated_by_name: str
