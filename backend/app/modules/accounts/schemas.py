import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.accounts.permissions import Role

USERNAME_PATTERN = r"^[a-z0-9._-]{3,40}$"
PASSWORD_MIN_LENGTH = 10


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=200)


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
    """Adds a person (or updates an existing one, found by phone). ``username`` and ``password`` are the login.
    The password is set here by the owner or platform admin; the person can change it later."""

    phone: str = Field(min_length=10, max_length=16)
    name: str = Field(min_length=1, max_length=120)
    name_ta: str | None = Field(default=None, max_length=200)
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=200)
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
    username: str | None
    role: Role
    location_ids: list[uuid.UUID] | None  # None = all locations
    is_active: bool


class StaffUpdate(BaseModel):
    """Only the fields sent are changed. ``location_ids: null`` means all locations.
    ``password`` resets the person's password (owner action)."""

    role: Role | None = None
    location_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=PASSWORD_MIN_LENGTH, max_length=200)


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
