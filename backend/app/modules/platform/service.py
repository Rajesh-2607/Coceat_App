import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import PlatformCtx
from app.core.db import set_tenant
from app.core.errors import NotFound, Unprocessable
from app.modules.audit import service as audit
from app.modules.platform.models import Business, VerticalTemplate
from app.modules.platform.schemas import (
    BusinessCreate,
    BusinessOut,
    BusinessUpdate,
    VerticalCreate,
    VerticalOut,
    VerticalUpdate,
)


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


async def list_businesses(ctx: PlatformCtx) -> list[BusinessOut]:
    rows = await ctx.db.scalars(select(Business).order_by(Business.created_at.desc()))
    return [BusinessOut.model_validate(b) for b in rows]


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
    return out


async def list_verticals(ctx: PlatformCtx) -> list[VerticalOut]:
    rows = await ctx.db.scalars(select(VerticalTemplate).order_by(VerticalTemplate.name))
    return [VerticalOut.model_validate(v) for v in rows]


async def create_vertical(ctx: PlatformCtx, data: VerticalCreate) -> VerticalOut:
    if await ctx.db.get(VerticalTemplate, data.key) is not None:
        raise Unprocessable("A vertical with this key already exists", code="vertical_key_taken")
    template = VerticalTemplate(
        key=data.key,
        name=data.name,
        name_ta=data.name_ta,
        default_modules=sorted({m.value for m in data.default_modules}),
        settings={},
    )
    ctx.db.add(template)
    await ctx.db.flush()
    out = VerticalOut.model_validate(template)
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
    before = VerticalOut.model_validate(template)
    changes = data.model_fields_set
    if "name" in changes and data.name is not None:
        template.name = data.name
    if "name_ta" in changes and data.name_ta is not None:
        template.name_ta = data.name_ta
    if "default_modules" in changes and data.default_modules is not None:
        template.default_modules = sorted({m.value for m in data.default_modules})
    await ctx.db.flush()
    await ctx.db.refresh(template)
    out = VerticalOut.model_validate(template)
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


async def get_business_for_admin(ctx: PlatformCtx, business_id: uuid.UUID) -> BusinessOut:
    return await get_business(ctx.db, business_id)


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
