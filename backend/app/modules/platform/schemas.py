import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.platform.modules import ModuleKey

# 2 digit state code, 10 char PAN, entity number, 'Z', checksum
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

BillingPeriod = Literal["trial", "monthly", "yearly"]
SubscriptionStatus = Literal["trial", "active", "past_due", "cancelled"]
PaymentStatus = Literal["ok", "failed"]


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


class AdminBusinessOut(BusinessOut):
    """BusinessOut plus the cross-business summary fields the admin list/detail views show."""

    location_count: int
    member_count: int
    plan_key: str | None
    plan_name: str | None
    plan_name_ta: str | None
    subscription_status: SubscriptionStatus | None


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


class WorkflowStep(BaseModel):
    step: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=60)


class WorkflowHighlight(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)


class VerticalOut(BaseModel):
    key: str
    name: str
    name_ta: str
    default_modules: list[str]
    # reference lists shown on the Configuration page — a starting point for a new business on this vertical,
    # not enforced anywhere: each business's own catalog (units, varieties) is set up in its own workspace.
    reference_units: list[str]
    reference_varieties: list[str]
    workflow_steps: list[WorkflowStep]
    workflow_highlights: list[WorkflowHighlight]


class VerticalCreate(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    name_ta: str = Field(min_length=1, max_length=120)
    default_modules: list[ModuleKey] = Field(default_factory=list)
    reference_units: list[str] = Field(default_factory=list)
    reference_varieties: list[str] = Field(default_factory=list)
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    workflow_highlights: list[WorkflowHighlight] = Field(default_factory=list)


class VerticalUpdate(BaseModel):
    """Only the fields sent are changed. Existing businesses on this vertical are not touched."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, min_length=1, max_length=120)
    default_modules: list[ModuleKey] | None = None
    reference_units: list[str] | None = None
    reference_varieties: list[str] | None = None
    workflow_steps: list[WorkflowStep] | None = None
    workflow_highlights: list[WorkflowHighlight] | None = None


# --- subscriptions -----------------------------------------------------------------------------------


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    name_ta: str
    price_paise: int | None  # null = "contact us"
    billing_period: BillingPeriod
    trial_days: int | None
    is_active: bool


class PlanCreate(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    name_ta: str = Field(min_length=1, max_length=120)
    price_paise: int | None = Field(default=None, ge=0, le=10**12)
    billing_period: BillingPeriod
    trial_days: int | None = Field(default=None, ge=1, le=365)


class PlanUpdate(BaseModel):
    """Only the fields sent are changed. Existing subscriptions on this plan keep their own price snapshot."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    name_ta: str | None = Field(default=None, min_length=1, max_length=120)
    price_paise: int | None = Field(default=None, ge=0, le=10**12)
    is_active: bool | None = None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    plan_key: str
    status: SubscriptionStatus
    price_paise: int | None
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancelled_at: datetime | None
    notes: str | None
    payment_status: PaymentStatus
    created_at: datetime


class SubscriptionWithBusinessOut(SubscriptionOut):
    business_name: str
    business_name_ta: str | None


class SubscriptionUpdate(BaseModel):
    """Only the fields sent are changed. Changing ``plan_key`` alone does not change status or dates."""

    plan_key: str | None = None
    status: SubscriptionStatus | None = None
    price_paise: int | None = Field(default=None, ge=0, le=10**12)
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)
    payment_status: PaymentStatus | None = None


class SubscriptionStatsOut(BaseModel):
    trial: int
    active: int
    past_due: int
    cancelled: int
    expiring_soon: int  # trial_ends_at or current_period_end within 7 days, still trial/active
    mrr_paise: int  # active+past_due subscriptions, normalized to a monthly amount (yearly / 12)
    payment_failures: int  # subscriptions with payment_status = 'failed'


# --- platform settings (singleton) --------------------------------------------------------------------


class NotificationPref(BaseModel):
    email: bool = True
    slack: bool = True


class PlatformSettingsOut(BaseModel):
    platform_name: str
    support_email: str
    default_currency: str
    default_trial_days: int
    default_plan_key: str | None
    invoice_prefix: str
    gst_rate_bp: int
    grace_period_days: int
    notification_prefs: dict[str, NotificationPref]


class PlatformSettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    platform_name: str | None = Field(default=None, min_length=1, max_length=120)
    support_email: str | None = Field(default=None, min_length=3, max_length=200)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    default_trial_days: int | None = Field(default=None, ge=1, le=365)
    default_plan_key: str | None = None
    invoice_prefix: str | None = Field(default=None, max_length=20)
    gst_rate_bp: int | None = Field(default=None, ge=0, le=10000)
    grace_period_days: int | None = Field(default=None, ge=0, le=90)
    notification_prefs: dict[str, NotificationPref] | None = None
