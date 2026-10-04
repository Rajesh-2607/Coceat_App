import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ledger.schemas import PaymentMethod

DocType = Literal["tax_invoice", "bill_of_supply"]
BillStatus = Literal["active", "void"]
SupplyType = Literal["intra", "inter"]

MAX_MONEY = 10**12


class SaleLineIn(BaseModel):
    product_id: uuid.UUID
    variety_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    unit_id: uuid.UUID  # the unit the price is quoted in (kg, dozen, ...)
    quantity: int = Field(ge=1, le=MAX_MONEY)  # base units: grams for weight products, pieces for count products
    unit_price_paise: int = Field(ge=0, le=MAX_MONEY)  # per unit, before GST


class SalePaymentIn(BaseModel):
    method: PaymentMethod
    amount_paise: int = Field(ge=1, le=MAX_MONEY)


class SaleIn(BaseModel):
    location_id: uuid.UUID
    party_id: uuid.UUID | None = None  # None = walk-in customer (must pay in full)
    place_of_supply: str | None = Field(
        default=None, pattern=r"^\d{2}$"
    )  # GST state code, for a walk-in in another state
    lines: list[SaleLineIn] = Field(min_length=1, max_length=100)
    payments: list[SalePaymentIn] = Field(default_factory=list, max_length=6)
    note: str | None = Field(default=None, max_length=300)


class BillLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    product_id: uuid.UUID
    variety_id: uuid.UUID | None
    grade_id: uuid.UUID | None
    unit_id: uuid.UUID
    description: str
    description_ta: str | None
    hsn_code: str | None
    unit_code: str
    unit_base_factor: int
    quantity_base: int
    unit_price_paise: int
    gst_rate_bp: int
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    returned_base: int = 0  # how much of this line has been taken back
    total_paise: int = 0  # taxable + tax


class BillPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: Literal["in", "out"]
    method: PaymentMethod
    amount_paise: int
    reversal_of: uuid.UUID | None
    created_at: datetime


class BillSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_number: str
    doc_type: DocType
    bill_date: date
    status: BillStatus
    location_id: uuid.UUID
    party_id: uuid.UUID | None
    party_name: str | None
    total_paise: int
    paid_paise: int
    created_at: datetime


class BillOut(BillSummaryOut):
    series: str
    party_phone: str | None
    party_gstin: str | None
    party_address: str | None
    seller_name: str
    seller_gstin: str | None
    seller_address: str | None
    seller_phone: str | None
    place_of_supply: str | None
    supply_type: SupplyType
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    round_off_paise: int
    credit_paise: int = 0  # left on the customer's account when the bill was made
    void_reason: str | None
    voided_at: datetime | None
    note: str | None
    created_by: uuid.UUID
    lines: list[BillLineOut] = []
    payments: list[BillPaymentOut] = []


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ReturnLineIn(BaseModel):
    bill_line_id: uuid.UUID
    quantity: int = Field(ge=1, le=MAX_MONEY)  # base units, at most what is still returnable


class ReturnIn(BaseModel):
    lines: list[ReturnLineIn] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=300)
    restock: bool = True  # False for goods that cannot be sold again
    location_id: uuid.UUID | None = None  # where restocked goods go; default: the bill's location
    refund_paise: int = Field(default=0, ge=0, le=MAX_MONEY)  # paid back now; the rest lowers what the party owes
    refund_method: PaymentMethod | None = None


class ReturnLineOut(BaseModel):
    bill_line_id: uuid.UUID
    description: str
    quantity_base: int
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int


class ReturnOut(BaseModel):
    id: uuid.UUID
    return_number: str
    bill_id: uuid.UUID
    bill_number: str
    return_date: date
    location_id: uuid.UUID | None
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    round_off_paise: int
    total_paise: int
    refund_paise: int
    refund_method: PaymentMethod | None
    reason: str
    created_at: datetime
    lines: list[ReturnLineOut]
