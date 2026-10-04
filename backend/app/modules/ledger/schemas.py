import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CrateDirection = Literal["issued", "returned"]
PaymentMethod = Literal["cash", "upi", "card", "bank", "cheque", "other"]
PaymentDirection = Literal["in", "out"]


class PartyLedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    party_id: uuid.UUID
    entry_type: str
    amount_paise: int
    reference_type: str | None
    reference_id: str | None
    reversal_of: uuid.UUID | None
    note: str | None
    created_by: uuid.UUID
    created_at: datetime


class PartyAdjustmentIn(BaseModel):
    """Manual correction. Positive: the party owes more; negative: owes less."""

    amount_paise: int = Field(ge=-(10**12), le=10**12)
    note: str = Field(min_length=3, max_length=300)  # a reason is mandatory


class CrateEntryIn(BaseModel):
    party_id: uuid.UUID
    direction: CrateDirection
    quantity: int = Field(ge=1, le=100_000)
    location_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=300)


class CrateAdjustmentIn(BaseModel):
    quantity: int = Field(ge=-100_000, le=100_000)  # signed
    note: str = Field(min_length=3, max_length=300)


class CrateLedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    party_id: uuid.UUID
    location_id: uuid.UUID | None
    entry_type: str
    quantity: int
    reference_type: str | None
    reference_id: str | None
    reversal_of: uuid.UUID | None
    note: str | None
    created_by: uuid.UUID
    created_at: datetime


class CrateBalanceOut(BaseModel):
    party_id: uuid.UUID
    crates_held: int


class PaymentIn(BaseModel):
    """A payment with no bill attached: a customer settling dues, or paying a supplier."""

    party_id: uuid.UUID
    direction: PaymentDirection
    method: PaymentMethod
    amount_paise: int = Field(ge=1, le=10**12)
    note: str | None = Field(default=None, max_length=300)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    party_id: uuid.UUID | None
    direction: PaymentDirection
    method: PaymentMethod
    amount_paise: int
    reference_type: str | None
    reference_id: str | None
    reversal_of: uuid.UUID | None
    note: str | None
    created_by: uuid.UUID
    created_at: datetime


class MethodTotal(BaseModel):
    method: PaymentMethod
    received_paise: int
    paid_paise: int


class ReverseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
