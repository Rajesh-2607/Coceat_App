import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class VerticalTemplate(TimestampMixin, Base):
    """Configuration for a trade (banana, flower, ...). New verticals are rows here, not code."""

    __tablename__ = "vertical_templates"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_ta: Mapped[str] = mapped_column(String(120))
    default_modules: Mapped[list[str]] = mapped_column(default=list)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Business(IdMixin, TimestampMixin, Base):
    """Platform table (not tenant-scoped): the tenant itself."""

    __tablename__ = "businesses"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
        CheckConstraint("gstin IS NULL OR length(gstin) = 15", name="gstin_length"),
    )

    name: Mapped[str] = mapped_column(String(120))
    name_ta: Mapped[str | None] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    address: Mapped[str | None] = mapped_column(String(300))  # printed on bills
    phone: Mapped[str | None] = mapped_column(String(16))
    vertical_key: Mapped[str] = mapped_column(ForeignKey("vertical_templates.key"))
    enabled_modules: Mapped[list[str]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # null = still in the setup queue; set once the platform team has finished onboarding this business
    setup_completed_at: Mapped[datetime | None]


class SubscriptionPlan(TimestampMixin, Base):
    """A plan the platform team can put a business on. Configuration rows, like VerticalTemplate.

    This is informational billing metadata only: what a business is meant to pay and when it renews.
    There is no payment gateway integration (online payment collection is out of v1 scope) — an operator
    records what was agreed or collected outside the system.
    """

    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("billing_period IN ('trial', 'monthly', 'yearly')", name="billing_period"),
        CheckConstraint("price_paise IS NULL OR price_paise >= 0", name="price"),
        CheckConstraint("trial_days IS NULL OR trial_days > 0", name="trial_days"),
    )

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_ta: Mapped[str] = mapped_column(String(120))
    price_paise: Mapped[int | None] = mapped_column(BigInteger)  # per billing_period; null = "contact us"
    billing_period: Mapped[str] = mapped_column(String(10))
    trial_days: Mapped[int | None]  # only meaningful when billing_period = 'trial'
    is_active: Mapped[bool] = mapped_column(default=True)  # retired plans stay for history, hidden from new picks


class Subscription(IdMixin, TimestampMixin, Base):
    """Which plan a business is on. One row per business; the row is edited in place (not append-only) —
    like Business.status, this is current state, and every change is already audited separately."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("business_id"),
        CheckConstraint("status IN ('trial', 'active', 'past_due', 'cancelled')", name="status"),
        CheckConstraint("price_paise IS NULL OR price_paise >= 0", name="price"),
        CheckConstraint("payment_status IN ('ok', 'failed')", name="payment_status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"))
    plan_key: Mapped[str] = mapped_column(ForeignKey("subscription_plans.key", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(10), default="trial")
    # snapshot at the time this was set, in case the plan's list price changes later (a bill line does the same)
    price_paise: Mapped[int | None] = mapped_column(BigInteger)
    trial_ends_at: Mapped[datetime | None]
    current_period_end: Mapped[datetime | None]  # next renewal date, for a paid plan
    cancelled_at: Mapped[datetime | None]
    notes: Mapped[str | None] = mapped_column(String(500))
    # informational only, set by an operator — there is no payment gateway, so nothing sets this automatically
    payment_status: Mapped[str] = mapped_column(String(10), default="ok")


class PlatformSettings(TimestampMixin, Base):
    """Platform-wide defaults, edited on the admin Settings page. Singleton: exactly one row (id='default')."""

    __tablename__ = "platform_settings"
    __table_args__ = (
        CheckConstraint("gst_rate_bp >= 0 AND gst_rate_bp <= 10000", name="gst_rate_bp"),
        CheckConstraint("default_trial_days > 0", name="default_trial_days"),
        CheckConstraint("grace_period_days >= 0", name="grace_period_days"),
    )

    id: Mapped[str] = mapped_column(String(10), primary_key=True, default="default")
    platform_name: Mapped[str] = mapped_column(String(120))
    support_email: Mapped[str] = mapped_column(String(200))
    default_currency: Mapped[str] = mapped_column(String(3), default="INR")
    default_trial_days: Mapped[int] = mapped_column(default=14)
    default_plan_key: Mapped[str | None] = mapped_column(ForeignKey("subscription_plans.key", ondelete="SET NULL"))
    invoice_prefix: Mapped[str] = mapped_column(String(20), default="")
    gst_rate_bp: Mapped[int] = mapped_column(default=1800)
    grace_period_days: Mapped[int] = mapped_column(default=7)
    # {event_key: {"email": bool, "slack": bool}} — preferences only; nothing actually dispatches yet (no
    # SMTP/Slack integration exists), same "informational, no live integration" stance as Subscription.
    notification_prefs: Mapped[dict[str, Any]] = mapped_column(default=dict)
