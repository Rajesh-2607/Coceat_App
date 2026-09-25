import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import PlatformCtx
from app.core.db import set_tenant
from app.core.errors import NotFound, Unprocessable
from app.modules.audit import service as audit
from app.modules.platform.models import Business, VerticalTemplate
from app.modules.platform.schemas import BusinessCreate, BusinessOut


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
