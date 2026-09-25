import uuid
from datetime import datetime
from typing import Literal

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
