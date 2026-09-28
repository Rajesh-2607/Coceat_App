import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.platform.modules import ModuleKey

# 2 digit state code, 10 char PAN, entity number, 'Z', checksum
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    gstin: str | None = None
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=16)
    vertical_key: str = Field(min_length=1, max_length=40)
    enabled_modules: list[ModuleKey] | None = None  # None = the vertical template's defaults

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().upper()
        if not GSTIN_RE.match(v):
            raise ValueError("invalid GSTIN format")
        return v


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_ta: str | None
    gstin: str | None
    address: str | None
    phone: str | None
    vertical_key: str
    enabled_modules: list[str]
    status: str
    setup_completed_at: datetime | None
    created_at: datetime


class WorkspaceContextOut(BaseModel):
    """What the workspace UI needs after login: which business, which modules, what this user may do."""

    business: BusinessOut
    role: str
    location_ids: list[uuid.UUID] | None
    permissions: list[str]


class BusinessUpdate(BaseModel):
    """Only the fields sent are changed. ``gstin: null`` clears the GSTIN."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    gstin: str | None = None
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=16)
    enabled_modules: list[ModuleKey] | None = None
    status: Literal["active", "suspended"] | None = None

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().upper()
        if not GSTIN_RE.match(v):
            raise ValueError("invalid GSTIN format")
        return v


class VerticalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    name_ta: str
    default_modules: list[str]


class VerticalCreate(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    name_ta: str = Field(min_length=1, max_length=120)
    default_modules: list[ModuleKey] = Field(default_factory=list)


class VerticalUpdate(BaseModel):
    """Only the fields sent are changed. Existing businesses on this vertical are not touched."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, min_length=1, max_length=120)
    default_modules: list[ModuleKey] | None = None
