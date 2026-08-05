from pydantic import BaseModel, ConfigDict, field_validator


class CommodityCreate(BaseModel):
    name: str
    code: str

    @field_validator("code")
    @classmethod
    def code_must_be_two_letters(cls, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise ValueError("code must be exactly 2 letters")
        return value.upper()


class CommodityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    commodity_id: int
    project_id: int
    name: str
    code: str
