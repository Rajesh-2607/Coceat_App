import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import PlatformCtx
from app.core.db import set_tenant
from app.core.errors import NotFound, Unprocessable
from app.modules.audit import service as audit
from app.modules.platform.models import Business, PlatformSettings, Subscription, SubscriptionPlan, VerticalTemplate
from app.modules.platform.schemas import (
    AdminBusinessOut,
    BusinessCreate,
    BusinessOut,
    BusinessUpdate,
    NotificationPref,
    PlanCreate,
    PlanOut,
    PlanUpdate,
    PlatformSettingsOut,
    PlatformSettingsUpdate,
    SubscriptionOut,
    SubscriptionStatsOut,
    SubscriptionUpdate,
    SubscriptionWithBusinessOut,
    VerticalCreate,
    VerticalOut,
    VerticalUpdate,
)

DEFAULT_PLAN_KEY = "trial"  # every new business starts here (see the seeded row in migration 0005)


@dataclass(frozen=True, slots=True)
class BusinessInfo:
    id: uuid.UUID
    name: str
    name_ta: str | None
    is_active: bool
    enabled_modules: frozenset[str]


def _info(b: Business) -> BusinessInfo:
    return BusinessInfo(b.id, b.name, b.name_ta, b.status == "active", frozenset(b.enabled_modules))


async def get_business_infos(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, BusinessInfo]:
    if not ids:
        return {}
    rows = await db.scalars(select(Business).where(Business.id.in_(ids)))
    return {b.id: _info(b) for b in rows}


async def get_business(db: AsyncSession, business_id: uuid.UUID) -> BusinessOut:
    business = await db.get(Business, business_id)
    if business is None:
        raise NotFound("Business not found")
    return BusinessOut.model_validate(business)


async def _admin_business_outs(ctx: PlatformCtx, businesses: list[Business]) -> list[AdminBusinessOut]:
    # deferred imports: accounts.service already imports platform.service, so importing it back at module
    # load time would cycle; inventory doesn't import platform, so that one could be top-level, but both are
    # kept local here to keep the two admin-summary lookups next to each other.
    from app.modules.accounts.service import member_counts_by_business
    from app.modules.inventory.service import location_counts_by_business

    ids = [b.id for b in businesses]
    subs = {
        s.business_id: (s, plan_name, plan_name_ta)
        for s, plan_name, plan_name_ta in (
            await ctx.db.execute(
                select(Subscription, SubscriptionPlan.name, SubscriptionPlan.name_ta)
                .join(SubscriptionPlan, SubscriptionPlan.key == Subscription.plan_key)
                .where(Subscription.business_id.in_(ids))
            )
        ).all()
    }
    locations = await location_counts_by_business(ctx.db, ids)
    members = await member_counts_by_business(ctx.db, ids)
    out = []
    for b in businesses:
        sub, plan_name, plan_name_ta = subs.get(b.id, (None, None, None))
        out.append(
            AdminBusinessOut(
                **BusinessOut.model_validate(b).model_dump(),
                location_count=locations.get(b.id, 0),
                member_count=members.get(b.id, 0),
                plan_key=sub.plan_key if sub else None,
                plan_name=plan_name,
                plan_name_ta=plan_name_ta,
                subscription_status=sub.status if sub else None,
            )
        )
    return out


async def list_businesses(ctx: PlatformCtx) -> list[AdminBusinessOut]:
    rows = list(await ctx.db.scalars(select(Business).order_by(Business.created_at.desc())))
    return await _admin_business_outs(ctx, rows)


async def create_business(ctx: PlatformCtx, data: BusinessCreate) -> BusinessOut:
    template = await ctx.db.get(VerticalTemplate, data.vertical_key)
    if template is None:
        raise Unprocessable("Unknown vertical", code="unknown_vertical")
    modules = [m.value for m in data.enabled_modules] if data.enabled_modules is not None else template.default_modules
    business = Business(
        name=data.name,
        name_ta=data.name_ta,
        gstin=data.gstin,
        address=data.address,
        phone=data.phone,
        vertical_key=template.key,
        enabled_modules=sorted(set(modules)),
    )
    ctx.db.add(business)
    await ctx.db.flush()
    out = BusinessOut.model_validate(business)
    # the event belongs to the new business so its owner sees it in "Who did what"
    await set_tenant(ctx.db, business.id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="business.create",
        actor_user_id=ctx.actor.user_id,
        business_id=business.id,
        entity_type="business",
        entity_id=business.id,
        after=audit.snapshot(out),
    )
    await _start_trial(ctx.db, business.id)
    return out


async def _start_trial(db: AsyncSession, business_id: uuid.UUID) -> None:
    """Every new business starts on the trial plan. Not audited on its own: it's part of business.create."""
    plan = await db.get(SubscriptionPlan, DEFAULT_PLAN_KEY)
    trial_days = plan.trial_days if plan else 14
    db.add(
        Subscription(
            business_id=business_id,
            plan_key=DEFAULT_PLAN_KEY,
            status="trial",
            price_paise=plan.price_paise if plan else 0,
            trial_ends_at=datetime.now(UTC) + timedelta(days=trial_days or 14),
        )
    )
    await db.flush()


def _vertical_out(t: VerticalTemplate) -> VerticalOut:
    settings = t.settings or {}
    return VerticalOut(
        key=t.key,
        name=t.name,
        name_ta=t.name_ta,
        default_modules=t.default_modules,
        reference_units=settings.get("reference_units", []),
        reference_varieties=settings.get("reference_varieties", []),
        workflow_steps=settings.get("workflow_steps", []),
        workflow_highlights=settings.get("workflow_highlights", []),
    )


async def list_verticals(ctx: PlatformCtx) -> list[VerticalOut]:
    rows = await ctx.db.scalars(select(VerticalTemplate).order_by(VerticalTemplate.name))
    return [_vertical_out(v) for v in rows]


async def create_vertical(ctx: PlatformCtx, data: VerticalCreate) -> VerticalOut:
    if await ctx.db.get(VerticalTemplate, data.key) is not None:
        raise Unprocessable("A vertical with this key already exists", code="vertical_key_taken")
    template = VerticalTemplate(
        key=data.key,
        name=data.name,
        name_ta=data.name_ta,
        default_modules=sorted({m.value for m in data.default_modules}),
        settings={
            "reference_units": list(data.reference_units),
            "reference_varieties": list(data.reference_varieties),
            "workflow_steps": [s.model_dump() for s in data.workflow_steps],
            "workflow_highlights": [h.model_dump() for h in data.workflow_highlights],
        },
    )
    ctx.db.add(template)
    await ctx.db.flush()
    out = _vertical_out(template)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="vertical.create",
        actor_user_id=ctx.actor.user_id,
        business_id=None,
        entity_type="vertical_template",
        entity_id=template.key,
        after=audit.snapshot(out),
    )
    return out


async def update_vertical(ctx: PlatformCtx, key: str, data: VerticalUpdate) -> VerticalOut:
    template = await ctx.db.get(VerticalTemplate, key)
    if template is None:
        raise NotFound("Vertical not found")
    before = _vertical_out(template)
    changes = data.model_fields_set
    if "name" in changes and data.name is not None:
        template.name = data.name
    if "name_ta" in changes and data.name_ta is not None:
        template.name_ta = data.name_ta
    if "default_modules" in changes and data.default_modules is not None:
        template.default_modules = sorted({m.value for m in data.default_modules})
    settings = dict(template.settings or {})
    if "reference_units" in changes and data.reference_units is not None:
        settings["reference_units"] = list(data.reference_units)
    if "reference_varieties" in changes and data.reference_varieties is not None:
        settings["reference_varieties"] = list(data.reference_varieties)
    if "workflow_steps" in changes and data.workflow_steps is not None:
        settings["workflow_steps"] = [s.model_dump() for s in data.workflow_steps]
    if "workflow_highlights" in changes and data.workflow_highlights is not None:
        settings["workflow_highlights"] = [h.model_dump() for h in data.workflow_highlights]
    template.settings = settings
    await ctx.db.flush()
    await ctx.db.refresh(template)
    out = _vertical_out(template)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="vertical.update",
        actor_user_id=ctx.actor.user_id,
        business_id=None,
        entity_type="vertical_template",
        entity_id=template.key,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out


async def setup_queue(ctx: PlatformCtx) -> list[BusinessOut]:
    """Active businesses the platform team has not yet finished onboarding, oldest first."""
    rows = await ctx.db.scalars(
        select(Business)
        .where(Business.setup_completed_at.is_(None), Business.status == "active")
        .order_by(Business.created_at)
    )
    return [BusinessOut.model_validate(b) for b in rows]


async def complete_setup(ctx: PlatformCtx, business_id: uuid.UUID) -> BusinessOut:
    business = await ctx.db.get(Business, business_id)
    if business is None:
        raise NotFound("Business not found")
    if business.setup_completed_at is not None:
        raise Unprocessable("Setup was already marked complete", code="setup_already_complete")
    before = BusinessOut.model_validate(business)
    business.setup_completed_at = datetime.now(UTC)
    await ctx.db.flush()
    await ctx.db.refresh(business)
    out = BusinessOut.model_validate(business)
    await set_tenant(ctx.db, business.id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="business.setup_complete",
        actor_user_id=ctx.actor.user_id,
        business_id=business.id,
        entity_type="business",
        entity_id=business.id,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out


async def get_business_for_admin(ctx: PlatformCtx, business_id: uuid.UUID) -> AdminBusinessOut:
    business = await ctx.db.get(Business, business_id)
    if business is None:
        raise NotFound("Business not found")
    return (await _admin_business_outs(ctx, [business]))[0]


async def update_business(ctx: PlatformCtx, business_id: uuid.UUID, data: BusinessUpdate) -> BusinessOut:
    business = await ctx.db.get(Business, business_id)
    if business is None:
        raise NotFound("Business not found")
    before = BusinessOut.model_validate(business)
    changes = data.model_fields_set
    if "name" in changes and data.name is not None:
        business.name = data.name
    if "name_ta" in changes:
        business.name_ta = data.name_ta
    if "gstin" in changes:
        business.gstin = data.gstin
    if "address" in changes:
        business.address = data.address
    if "phone" in changes:
        business.phone = data.phone
    if "enabled_modules" in changes and data.enabled_modules is not None:
        business.enabled_modules = sorted({m.value for m in data.enabled_modules})
    if "status" in changes and data.status is not None:
        business.status = data.status
    await ctx.db.flush()
    await ctx.db.refresh(business)
    out = BusinessOut.model_validate(business)
    await set_tenant(ctx.db, business.id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="business.update",
        actor_user_id=ctx.actor.user_id,
        business_id=business.id,
        entity_type="business",
        entity_id=business.id,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out


# --- subscription plans (catalog, admin-configurable like verticals) ---------------------------------


async def list_plans(ctx: PlatformCtx, *, include_inactive: bool = True) -> list[PlanOut]:
    stmt = select(SubscriptionPlan).order_by(SubscriptionPlan.price_paise.is_(None), SubscriptionPlan.price_paise)
    if not include_inactive:
        stmt = stmt.where(SubscriptionPlan.is_active.is_(True))
    return [PlanOut.model_validate(p) for p in await ctx.db.scalars(stmt)]


async def create_plan(ctx: PlatformCtx, data: PlanCreate) -> PlanOut:
    if await ctx.db.get(SubscriptionPlan, data.key) is not None:
        raise Unprocessable("A plan with this key already exists", code="plan_key_taken")
    if data.billing_period == "trial" and not data.trial_days:
        raise Unprocessable("A trial plan needs a number of trial days", code="trial_days_required")
    plan = SubscriptionPlan(
        key=data.key,
        name=data.name,
        name_ta=data.name_ta,
        price_paise=data.price_paise,
        billing_period=data.billing_period,
        trial_days=data.trial_days,
    )
    ctx.db.add(plan)
    await ctx.db.flush()
    out = PlanOut.model_validate(plan)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="plan.create",
        actor_user_id=ctx.actor.user_id,
        business_id=None,
        entity_type="subscription_plan",
        entity_id=plan.key,
        after=audit.snapshot(out),
    )
    return out


async def update_plan(ctx: PlatformCtx, key: str, data: PlanUpdate) -> PlanOut:
    plan = await ctx.db.get(SubscriptionPlan, key)
    if plan is None:
        raise NotFound("Plan not found")
    before = PlanOut.model_validate(plan)
    changes = data.model_fields_set
    if "name" in changes and data.name is not None:
        plan.name = data.name
    if "name_ta" in changes and data.name_ta is not None:
        plan.name_ta = data.name_ta
    if "price_paise" in changes:
        plan.price_paise = data.price_paise
    if "is_active" in changes and data.is_active is not None:
        plan.is_active = data.is_active
    await ctx.db.flush()
    await ctx.db.refresh(plan)
    out = PlanOut.model_validate(plan)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="plan.update",
        actor_user_id=ctx.actor.user_id,
        business_id=None,
        entity_type="subscription_plan",
        entity_id=plan.key,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out


# --- subscriptions (one per business) -------------------------------------------------------------------


async def _subscription(ctx: PlatformCtx, business_id: uuid.UUID) -> Subscription:
    sub = await ctx.db.scalar(select(Subscription).where(Subscription.business_id == business_id))
    if sub is None:
        raise NotFound("Subscription not found")
    return sub


async def get_subscription(ctx: PlatformCtx, business_id: uuid.UUID) -> SubscriptionOut:
    return SubscriptionOut.model_validate(await _subscription(ctx, business_id))


async def update_subscription(ctx: PlatformCtx, business_id: uuid.UUID, data: SubscriptionUpdate) -> SubscriptionOut:
    sub = await _subscription(ctx, business_id)
    changes = data.model_fields_set
    if (
        "plan_key" in changes
        and data.plan_key is not None
        and await ctx.db.get(SubscriptionPlan, data.plan_key) is None
    ):
        raise Unprocessable("Unknown plan", code="unknown_plan")
    before = SubscriptionOut.model_validate(sub)
    if "plan_key" in changes and data.plan_key is not None:
        sub.plan_key = data.plan_key
    if "status" in changes and data.status is not None:
        sub.status = data.status
        if data.status == "cancelled" and sub.cancelled_at is None:
            sub.cancelled_at = datetime.now(UTC)
        elif data.status != "cancelled":
            sub.cancelled_at = None
    if "price_paise" in changes:
        sub.price_paise = data.price_paise
    if "trial_ends_at" in changes:
        sub.trial_ends_at = data.trial_ends_at
    if "current_period_end" in changes:
        sub.current_period_end = data.current_period_end
    if "notes" in changes:
        sub.notes = data.notes
    if "payment_status" in changes and data.payment_status is not None:
        sub.payment_status = data.payment_status
    await ctx.db.flush()
    await ctx.db.refresh(sub)
    out = SubscriptionOut.model_validate(sub)
    await set_tenant(ctx.db, business_id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="subscription.update",
        actor_user_id=ctx.actor.user_id,
        business_id=business_id,
        entity_type="subscription",
        entity_id=sub.id,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out


async def list_subscriptions(ctx: PlatformCtx, *, status: str | None = None) -> list[SubscriptionWithBusinessOut]:
    stmt = (
        select(Subscription, Business.name, Business.name_ta)
        .join(Business, Business.id == Subscription.business_id)
        .order_by(Subscription.created_at.desc())
    )
    if status:
        stmt = stmt.where(Subscription.status == status)
    rows = (await ctx.db.execute(stmt)).all()
    return [
        SubscriptionWithBusinessOut(
            **SubscriptionOut.model_validate(sub).model_dump(), business_name=name, business_name_ta=name_ta
        )
        for sub, name, name_ta in rows
    ]


async def subscription_stats(ctx: PlatformCtx) -> SubscriptionStatsOut:
    counts = dict((await ctx.db.execute(select(Subscription.status, func.count()).group_by(Subscription.status))).all())
    soon = datetime.now(UTC) + timedelta(days=7)
    expiring = await ctx.db.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(
            Subscription.status.in_(("trial", "active")),
            (
                (Subscription.status == "trial")
                & Subscription.trial_ends_at.is_not(None)
                & (Subscription.trial_ends_at <= soon)
            )
            | (
                (Subscription.status == "active")
                & Subscription.current_period_end.is_not(None)
                & (Subscription.current_period_end <= soon)
            ),
        )
    )
    payment_failures = await ctx.db.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.payment_status == "failed")
    )
    # MRR: active subscriptions' price, normalized to a monthly figure (a yearly plan divides by 12).
    mrr_rows = (
        await ctx.db.execute(
            select(Subscription.price_paise, SubscriptionPlan.billing_period)
            .join(SubscriptionPlan, SubscriptionPlan.key == Subscription.plan_key)
            .where(Subscription.status == "active", Subscription.price_paise.is_not(None))
        )
    ).all()
    mrr_paise = sum((price // 12 if period == "yearly" else price) for price, period in mrr_rows if price is not None)
    return SubscriptionStatsOut(
        trial=counts.get("trial", 0),
        active=counts.get("active", 0),
        past_due=counts.get("past_due", 0),
        cancelled=counts.get("cancelled", 0),
        expiring_soon=expiring or 0,
        mrr_paise=mrr_paise,
        payment_failures=payment_failures or 0,
    )


# --- platform settings (singleton) --------------------------------------------------------------------

PLATFORM_SETTINGS_ID = "default"


async def _platform_settings(ctx: PlatformCtx) -> PlatformSettings:
    settings = await ctx.db.get(PlatformSettings, PLATFORM_SETTINGS_ID)
    if settings is None:
        raise NotFound("Platform settings not found")
    return settings


def _platform_settings_out(s: PlatformSettings) -> PlatformSettingsOut:
    return PlatformSettingsOut(
        platform_name=s.platform_name,
        support_email=s.support_email,
        default_currency=s.default_currency,
        default_trial_days=s.default_trial_days,
        default_plan_key=s.default_plan_key,
        invoice_prefix=s.invoice_prefix,
        gst_rate_bp=s.gst_rate_bp,
        grace_period_days=s.grace_period_days,
        notification_prefs={k: NotificationPref(**v) for k, v in (s.notification_prefs or {}).items()},
    )


async def get_platform_settings(ctx: PlatformCtx) -> PlatformSettingsOut:
    return _platform_settings_out(await _platform_settings(ctx))


async def update_platform_settings(ctx: PlatformCtx, data: PlatformSettingsUpdate) -> PlatformSettingsOut:
    settings = await _platform_settings(ctx)
    changes = data.model_fields_set
    if (
        "default_plan_key" in changes
        and data.default_plan_key is not None
        and await ctx.db.get(SubscriptionPlan, data.default_plan_key) is None
    ):
        raise Unprocessable("Unknown plan", code="unknown_plan")
    before = _platform_settings_out(settings)
    if "platform_name" in changes and data.platform_name is not None:
        settings.platform_name = data.platform_name
    if "support_email" in changes and data.support_email is not None:
        settings.support_email = data.support_email
    if "default_currency" in changes and data.default_currency is not None:
        settings.default_currency = data.default_currency.upper()
    if "default_trial_days" in changes and data.default_trial_days is not None:
        settings.default_trial_days = data.default_trial_days
    if "default_plan_key" in changes:
        settings.default_plan_key = data.default_plan_key
    if "invoice_prefix" in changes and data.invoice_prefix is not None:
        settings.invoice_prefix = data.invoice_prefix
    if "gst_rate_bp" in changes and data.gst_rate_bp is not None:
        settings.gst_rate_bp = data.gst_rate_bp
    if "grace_period_days" in changes and data.grace_period_days is not None:
        settings.grace_period_days = data.grace_period_days
    if "notification_prefs" in changes and data.notification_prefs is not None:
        settings.notification_prefs = {k: v.model_dump() for k, v in data.notification_prefs.items()}
    await ctx.db.flush()
    await ctx.db.refresh(settings)
    out = _platform_settings_out(settings)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="platform_settings.update",
        actor_user_id=ctx.actor.user_id,
        business_id=None,
        entity_type="platform_settings",
        entity_id=PLATFORM_SETTINGS_ID,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out
