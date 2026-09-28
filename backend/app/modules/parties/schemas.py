import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.platform.schemas import GSTIN_RE

PartyKind = Literal["customer", "supplier"]


def _clean_gstin(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    v = v.strip().upper()
    if not GSTIN_RE.match(v):
        raise ValueError("invalid GSTIN format")
    return v


class PartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=16)
    address: str | None = Field(default=None, max_length=300)
    gstin: str | None = None
    credit_limit_paise: int | None = Field(default=None, ge=0, le=10**12)
    notes: str | None = Field(default=None, max_length=500)
    # > 0: they owe you; < 0: you owe them. Written to the party ledger as an 'opening' entry.
    opening_balance_paise: int = Field(default=0, ge=-(10**12), le=10**12)

    _gstin = field_validator("gstin")(_clean_gstin)


class PartyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=16)
    address: str | None = Field(default=None, max_length=300)
    gstin: str | None = None
    credit_limit_paise: int | None = Field(default=None, ge=0, le=10**12)
    notes: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    _gstin = field_validator("gstin")(_clean_gstin)


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: PartyKind
    name: str
    name_ta: str | None
    phone: str | None
    address: str | None
    gstin: str | None
    credit_limit_paise: int | None
    notes: str | None
    is_active: bool
    balance_paise: int = 0  # > 0 they owe you; < 0 you owe them
    crates_held: int = 0
    created_at: datetime
    updated_at: datetime


class PartyBalanceOut(BaseModel):
    party_id: uuid.UUID
    name: str
    name_ta: str | None
    balance_paise: int


class PartySummaryOut(BaseModel):
    count: int
    owed_to_us_paise: int  # sum of balances where the party owes the business
    we_owe_paise: int  # sum of balances where the business owes the party (positive number)
    top_owing: list[PartyBalanceOut]  # parties that owe the most
