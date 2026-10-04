import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

LocationKind = Literal["shop", "godown", "cold_storage", "other"]


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, max_length=120)
    kind: LocationKind = "shop"


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, max_length=120)
    kind: LocationKind | None = None
    is_active: bool | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_ta: str | None
    kind: LocationKind
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- stock ---------------------------------------------------------------------------------------------

WastageReason = Literal["rotten", "damaged", "shrinkage", "spoiled_in_transit", "other"]
MovementType = Literal[
    "opening",
    "adjustment",
    "transfer_out",
    "transfer_in",
    "wastage",
    "reversal",
    "purchase",
    "sale",
    "sale_return",
]

# quantities are integers in the product's base unit: grams for weight products, pieces for count products
BaseQty = Annotated[int, Field(ge=1, le=10**12)]


class StockItemIn(BaseModel):
    product_id: uuid.UUID
    variety_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None


class OpeningStockIn(StockItemIn):
    location_id: uuid.UUID
    quantity: BaseQty
    note: str | None = Field(default=None, max_length=300)


class StockAdjustmentIn(StockItemIn):
    location_id: uuid.UUID
    quantity: int = Field(ge=-(10**12), le=10**12)  # signed, never 0
    reason: str = Field(min_length=3, max_length=300)  # mandatory


class TransferLineIn(StockItemIn):
    quantity: BaseQty


class TransferIn(BaseModel):
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    lines: list[TransferLineIn] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=300)


class WastageIn(StockItemIn):
    location_id: uuid.UUID
    quantity: BaseQty
    reason_code: WastageReason
    note: str | None = Field(default=None, max_length=300)


class ReverseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    location_id: uuid.UUID
    product_id: uuid.UUID
    variety_id: uuid.UUID | None
    grade_id: uuid.UUID | None
    quantity: int
    movement_type: MovementType
    reference_type: str | None
    reference_id: str | None
    reversal_of: uuid.UUID | None
    reason: str | None
    created_by: uuid.UUID
    created_at: datetime


class StockBalanceOut(BaseModel):
    location_id: uuid.UUID
    product_id: uuid.UUID
    variety_id: uuid.UUID | None
    grade_id: uuid.UUID | None
    quantity: int  # base units
    kind: Literal["weight", "count"]
    product_name: str
    product_name_ta: str | None
    variety_name: str | None
    variety_name_ta: str | None
    grade_name: str | None
    grade_name_ta: str | None


class TransferOut(BaseModel):
    id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    note: str | None
    created_by: uuid.UUID
    created_at: datetime
    movements: list[StockMovementOut]


class WastageOut(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    product_id: uuid.UUID
    variety_id: uuid.UUID | None
    grade_id: uuid.UUID | None
    quantity: int
    reason_code: WastageReason
    note: str | None
    movement_id: uuid.UUID
    reversed: bool
    created_by: uuid.UUID
    created_at: datetime
