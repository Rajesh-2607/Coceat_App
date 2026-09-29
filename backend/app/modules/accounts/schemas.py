import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.accounts.permissions import Role


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=10, max_length=16)


class OtpRequestOut(BaseModel):
    challenge_id: uuid.UUID
    expires_in_seconds: int


class OtpVerifyIn(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


class MembershipOut(BaseModel):
    business_id: uuid.UUID
    business_name: str
    business_name_ta: str | None
    role: Role


class MeOut(BaseModel):
    id: uuid.UUID
    name: str
    name_ta: str | None
    language: str
    is_platform_admin: bool
    current_business_id: uuid.UUID | None
    memberships: list[MembershipOut]


class SelectBusinessIn(BaseModel):
    business_id: uuid.UUID


class MemberIn(BaseModel):
    phone: str = Field(min_length=10, max_length=16)
    name: str = Field(min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    role: Role
    location_ids: list[uuid.UUID] | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID
    role: Role
    location_ids: list[uuid.UUID] | None
    is_active: bool


class StaffOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    name_ta: str | None
    phone: str
    role: Role
    location_ids: list[uuid.UUID] | None  # None = all locations
    is_active: bool


class StaffUpdate(BaseModel):
    """Only the fields sent are changed. ``location_ids: null`` means all locations."""

    role: Role | None = None
    location_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None


class PlatformMembershipOut(BaseModel):
    business_id: uuid.UUID
    business_name: str
    role: Role
    is_active: bool


class PlatformUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    name: str
    name_ta: str | None
    language: str
    is_platform_admin: bool
    is_active: bool
    # descriptive only (see User model) — never used for authorization
    platform_role_title: str | None
    platform_scope_note: str | None
    memberships: list[PlatformMembershipOut] = []


class PlatformUserUpdate(BaseModel):
    """Only the fields sent are changed."""

    is_active: bool | None = None
    is_platform_admin: bool | None = None
    platform_role_title: str | None = Field(default=None, max_length=60)
    platform_scope_note: str | None = Field(default=None, max_length=120)
