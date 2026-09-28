import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

QuantityKind = Literal["weight", "count"]

# GST slabs in basis points (500 = 5%). Fresh fruit and vegetables are usually 0 (exempt).
GST_RATES_BP = (0, 25, 300, 500, 1200, 1800, 2800)


def _check_rate(v: int | None) -> int | None:
    if v is not None and v not in GST_RATES_BP:
        raise ValueError("unsupported GST rate")
    return v


class UnitCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=60)
    name_ta: str | None = Field(default=None, max_length=100)
    kind: QuantityKind
    base_factor: int = Field(ge=1, le=1_000_000_000)  # grams (weight) or pieces (count) per unit


class UnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    name_ta: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    name_ta: str | None
    kind: QuantityKind
    base_factor: int
    is_active: bool


class GradeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    name_ta: str | None = Field(default=None, max_length=80)


class GradeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    name_ta: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class GradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_ta: str | None
    is_active: bool


class VarietyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, max_length=120)


class VarietyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class VarietyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    name_ta: str | None
    is_active: bool


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    kind: QuantityKind
    unit_id: uuid.UUID
    default_price_paise: int | None = Field(default=None, ge=0, le=10**12)
    gst_rate_bp: int = 0
    hsn_code: str | None = Field(default=None, max_length=8, pattern=r"^\d{4,8}$")

    _rate = field_validator("gst_rate_bp")(_check_rate)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    unit_id: uuid.UUID | None = None
    default_price_paise: int | None = Field(default=None, ge=0, le=10**12)
    gst_rate_bp: int | None = None
    hsn_code: str | None = Field(default=None, max_length=8, pattern=r"^\d{4,8}$")
    is_active: bool | None = None

    _rate = field_validator("gst_rate_bp")(_check_rate)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_ta: str | None
    kind: QuantityKind
    unit_id: uuid.UUID
    default_price_paise: int | None
    gst_rate_bp: int
    hsn_code: str | None
    is_active: bool
    varieties: list[VarietyOut] = []
    created_at: datetime
    updated_at: datetime
