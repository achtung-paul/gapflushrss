from pydantic import BaseModel, ConfigDict, field_validator


class ProcessTypeCreate(BaseModel):
    name: str


class ProcessTypeUpdate(BaseModel):
    name: str


class ProcessTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    process_type_id: int
    name: str


class ToleranceGroupCreate(BaseModel):
    name: str


class ToleranceGroupUpdate(BaseModel):
    name: str


class ToleranceGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tolerance_group_id: int
    process_type_id: int
    sequence_number: int
    name: str


class DimensionRangeCreate(BaseModel):
    min_value: float
    max_value: float

    @field_validator("max_value")
    @classmethod
    def max_must_exceed_min(cls, max_value: float, info) -> float:
        min_value = info.data.get("min_value")
        if min_value is not None and max_value <= min_value:
            raise ValueError("max_value must be greater than min_value")
        return max_value


class DimensionRangeUpdate(DimensionRangeCreate):
    pass


class DimensionRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension_range_id: int
    process_type_id: int
    sequence_number: int
    min_value: float
    max_value: float


class ToleranceValueCellIn(BaseModel):
    # Both are optional -- the DIN table legitimately leaves many cells
    # blank (a tolerance group with no defined value at that range).
    tool_value: float | None = None
    non_tool_value: float | None = None


class ToleranceValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tolerance_value_id: int
    tolerance_group_id: int
    dimension_range_id: int
    tool_value: float | None
    non_tool_value: float | None
