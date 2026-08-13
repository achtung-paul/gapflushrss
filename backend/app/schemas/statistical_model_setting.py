from pydantic import BaseModel, ConfigDict, model_validator


class StatisticalModelSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sigma_level: int
    visible: bool
    info_only: bool


class StatisticalModelSettingIn(BaseModel):
    sigma_level: int
    visible: bool
    info_only: bool


class StatisticalModelSettingsUpdate(BaseModel):
    settings: list[StatisticalModelSettingIn]

    @model_validator(mode="after")
    def must_cover_every_level_exactly_once(self) -> "StatisticalModelSettingsUpdate":
        # Every client always has exactly one row per sigma level 1-5
        # (see models/statistical_model_setting.py) -- a partial update
        # would leave that invariant's caller (update_statistical_model_
        # settings in api/reference_data.py) unable to tell "the admin
        # meant to leave the rest alone" apart from "the admin meant to
        # delete them", so this requires the whole set every time instead.
        levels = sorted(item.sigma_level for item in self.settings)
        if levels != [1, 2, 3, 4, 5]:
            raise ValueError("settings must include exactly sigma levels 1 through 5, each once")
        return self
