from fastapi import APIRouter, status

from app.core.deps import AdminCtx
from app.modules.platform import service
from app.modules.platform.schemas import BusinessCreate, BusinessOut

router = APIRouter(prefix="/admin/businesses", tags=["admin"])


@router.get("", response_model=list[BusinessOut])
async def list_businesses(ctx: AdminCtx) -> list[BusinessOut]:
    return await service.list_businesses(ctx)


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
async def create_business(body: BusinessCreate, ctx: AdminCtx) -> BusinessOut:
    out = await service.create_business(ctx, body)
    await ctx.db.commit()
    return out
