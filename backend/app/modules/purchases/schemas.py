import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ledger.schemas import PaymentMethod

MAX_MONEY = 10**12


class PurchaseLineIn(BaseModel):
    product_id: uuid.UUID
    variety_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    unit_id: uuid.UUID  # the unit the cost is quoted in
    quantity: int = Field(ge=1, le=MAX_MONEY)  # base units: grams or pieces
    unit_cost_paise: int = Field(ge=0, le=MAX_MONEY)  # per unit


class PurchasePaymentIn(BaseModel):
    method: PaymentMethod
    amount_paise: int = Field(ge=1, le=MAX_MONEY)


class PurchaseIn(BaseModel):
    supplier_id: uuid.UUID
    location_id: uuid.UUID
    purchase_date: date | None = None  # default today; never in the future
    supplier_bill_no: str | None = Field(default=None, max_length=40)
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=100)
    payments: list[PurchasePaymentIn] = Field(default_factory=list, max_length=6)
    note: str | None = Field(default=None, max_length=300)


class PurchaseLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    product_id: uuid.UUID
    variety_id: uuid.UUID | None
    grade_id: uuid.UUID | None
    unit_id: uuid.UUID
    description: str
    description_ta: str | None
    unit_code: str
    unit_base_factor: int
    quantity_base: int
    unit_cost_paise: int
    amount_paise: int


class PurchasePaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: Literal["in", "out"]
    method: PaymentMethod
    amount_paise: int
    reversal_of: uuid.UUID | None
    created_at: datetime


class PurchaseSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    purchase_number: str
    purchase_date: date
    status: Literal["active", "void"]
    supplier_id: uuid.UUID
    supplier_name: str
    location_id: uuid.UUID
    supplier_bill_no: str | None
    total_paise: int
    paid_paise: int
    created_at: datetime


class PurchaseOut(PurchaseSummaryOut):
    credit_paise: int = 0  # owed to the supplier after this purchase
    void_reason: str | None
    voided_at: datetime | None
    note: str | None
    created_by: uuid.UUID
    lines: list[PurchaseLineOut] = []
    payments: list[PurchasePaymentOut] = []


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
