import uuid

from fastapi import APIRouter, status

from app.core.deps import AdminCtx
from app.modules.catalog import service as catalog
from app.modules.platform import service
from app.modules.platform.schemas import (
    BusinessCreate,
    BusinessOut,
    BusinessUpdate,
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


@router.get("/businesses", response_model=list[BusinessOut])
async def list_businesses(ctx: AdminCtx) -> list[BusinessOut]:
    return await service.list_businesses(ctx)


@router.post("/businesses", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def create_business(body: BusinessCreate, ctx: AdminCtx) -> BusinessOut:
    out = await service.create_business(ctx, body)
    # the new business's starting units (kg, crate, ...): same transaction, tenant context already set to it
    await catalog.seed_default_units(ctx.db, out.id)
    await ctx.db.commit()
    return out


@router.get("/businesses/{business_id}", response_model=BusinessOut)
async def get_business(business_id: uuid.UUID, ctx: AdminCtx) -> BusinessOut:
    return await service.get_business_for_admin(ctx, business_id)


@router.patch("/businesses/{business_id}", response_model=BusinessOut)
async def update_business(business_id: uuid.UUID, body: BusinessUpdate, ctx: AdminCtx) -> BusinessOut:
    out = await service.update_business(ctx, business_id, body)
    await ctx.db.commit()
    return out
