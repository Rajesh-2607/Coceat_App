import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import AdminCtx
from app.modules.catalog import service as catalog
from app.modules.platform import service
from app.modules.platform.schemas import (
    AdminBusinessOut,
    BusinessCreate,
    BusinessOut,
    BusinessUpdate,
    PlanCreate,
    PlanOut,
    PlanUpdate,
    PlatformSettingsOut,
    PlatformSettingsUpdate,
    SubscriptionOut,
    SubscriptionStatsOut,
    SubscriptionStatus,
    SubscriptionUpdate,
    SubscriptionWithBusinessOut,
    VerticalCreate,
    VerticalOut,
    VerticalUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/verticals", response_model=list[VerticalOut])
async def list_verticals(ctx: AdminCtx) -> list[VerticalOut]:
    return await service.list_verticals(ctx)


@router.post("/verticals", response_model=VerticalOut, status_code=status.HTTP_201_CREATED)
async def create_vertical(body: VerticalCreate, ctx: AdminCtx) -> VerticalOut:
    out = await service.create_vertical(ctx, body)
    await ctx.db.commit()
    return out


@router.patch("/verticals/{key}", response_model=VerticalOut)
async def update_vertical(key: str, body: VerticalUpdate, ctx: AdminCtx) -> VerticalOut:
    out = await service.update_vertical(ctx, key, body)
    await ctx.db.commit()
    return out


@router.get("/setup-queue", response_model=list[BusinessOut])
async def setup_queue(ctx: AdminCtx) -> list[BusinessOut]:
    return await service.setup_queue(ctx)


@router.post("/businesses/{business_id}/complete-setup", response_model=BusinessOut)
async def complete_setup(business_id: uuid.UUID, ctx: AdminCtx) -> BusinessOut:
    out = await service.complete_setup(ctx, business_id)
    await ctx.db.commit()
    return out


@router.get("/businesses", response_model=list[AdminBusinessOut])
async def list_businesses(ctx: AdminCtx) -> list[AdminBusinessOut]:
    return await service.list_businesses(ctx)


@router.post("/businesses", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def create_business(body: BusinessCreate, ctx: AdminCtx) -> BusinessOut:
    out = await service.create_business(ctx, body)
    # the new business's starting units (kg, crate, ...): same transaction, tenant context already set to it
    await catalog.seed_default_units(ctx.db, out.id)
    await ctx.db.commit()
    return out


@router.get("/businesses/{business_id}", response_model=AdminBusinessOut)
async def get_business(business_id: uuid.UUID, ctx: AdminCtx) -> AdminBusinessOut:
    return await service.get_business_for_admin(ctx, business_id)


@router.patch("/businesses/{business_id}", response_model=BusinessOut)
async def update_business(business_id: uuid.UUID, body: BusinessUpdate, ctx: AdminCtx) -> BusinessOut:
    out = await service.update_business(ctx, business_id, body)
    await ctx.db.commit()
    return out


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(ctx: AdminCtx, include_inactive: Annotated[bool, Query()] = True) -> list[PlanOut]:
    return await service.list_plans(ctx, include_inactive=include_inactive)


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(body: PlanCreate, ctx: AdminCtx) -> PlanOut:
    out = await service.create_plan(ctx, body)
    await ctx.db.commit()
    return out


@router.patch("/plans/{key}", response_model=PlanOut)
async def update_plan(key: str, body: PlanUpdate, ctx: AdminCtx) -> PlanOut:
    out = await service.update_plan(ctx, key, body)
    await ctx.db.commit()
    return out


@router.get("/subscriptions", response_model=list[SubscriptionWithBusinessOut])
async def list_subscriptions(
    ctx: AdminCtx, sub_status: Annotated[SubscriptionStatus | None, Query(alias="status")] = None
) -> list[SubscriptionWithBusinessOut]:
    return await service.list_subscriptions(ctx, status=sub_status)


@router.get("/subscriptions/stats", response_model=SubscriptionStatsOut)
async def subscription_stats(ctx: AdminCtx) -> SubscriptionStatsOut:
    return await service.subscription_stats(ctx)


@router.get("/businesses/{business_id}/subscription", response_model=SubscriptionOut)
async def get_subscription(business_id: uuid.UUID, ctx: AdminCtx) -> SubscriptionOut:
    return await service.get_subscription(ctx, business_id)


@router.patch("/businesses/{business_id}/subscription", response_model=SubscriptionOut)
async def update_subscription(business_id: uuid.UUID, body: SubscriptionUpdate, ctx: AdminCtx) -> SubscriptionOut:
    out = await service.update_subscription(ctx, business_id, body)
    await ctx.db.commit()
    return out


@router.get("/settings", response_model=PlatformSettingsOut)
async def get_platform_settings(ctx: AdminCtx) -> PlatformSettingsOut:
    return await service.get_platform_settings(ctx)


@router.patch("/settings", response_model=PlatformSettingsOut)
async def update_platform_settings(body: PlatformSettingsUpdate, ctx: AdminCtx) -> PlatformSettingsOut:
    out = await service.update_platform_settings(ctx, body)
    await ctx.db.commit()
    return out
