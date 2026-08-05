from pydantic import BaseModel, ConfigDict


class ProcessTypeCreate(BaseModel):
    name: str


class ProcessTypeUpdate(BaseModel):
    name: str


class ProcessTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    process_type_id: int
    name: str


class ToleranceClassCreate(BaseModel):
    class_name: str
    value: float


class ToleranceClassUpdate(BaseModel):
    class_name: str
    value: float


class ToleranceClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tolerance_class_id: int
    process_type_id: int
    class_name: str
    value: float
