from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.chain_component import ContributorType


class StandardToleranceCreate(BaseModel):
    name: str
    # Symmetric +/- magnitude in mm, same shape as ChainComponentCreate.tolerance_value.
    tolerance_value: float
    # Which contributor type a chain component created from this preset
    # should save as (see ToleranceChainSection.jsx's merged Type
    # dropdown). Defaulted so an older client that doesn't send this
    # still validates.
    contributor_type: ContributorType = ContributorType.COMPONENT

    @field_validator("tolerance_value")
    @classmethod
    def must_not_be_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("tolerance_value must be given as a positive magnitude")
        return value

    @field_validator("name")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class StandardToleranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    standard_tolerance_id: int
    name: str
    tolerance_value: float
    contributor_type: ContributorType
    updated_by_name: str
    updated_at: datetime
