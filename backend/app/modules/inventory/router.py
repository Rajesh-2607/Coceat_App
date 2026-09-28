import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.inventory import service
from app.modules.inventory.schemas import (
    LocationCreate,
    LocationOut,
    LocationUpdate,
    OpeningStockIn,
    ReverseIn,
    StockAdjustmentIn,
    StockBalanceOut,
    StockMovementOut,
    TransferIn,
    TransferOut,
    WastageIn,
    WastageOut,
)

router = APIRouter(prefix="/w/locations", tags=["inventory"])


@router.get("", response_model=list[LocationOut])
async def list_locations(ctx: WorkspaceCtx) -> list[LocationOut]:
    return await service.list_locations(ctx)


@router.get("/{location_id}", response_model=LocationOut)
async def get_location(location_id: uuid.UUID, ctx: WorkspaceCtx) -> LocationOut:
    return await service.get_location(ctx, location_id)


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
async def create_location(body: LocationCreate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "location.create", body, lambda: service.create_location(ctx, body), status_code=201
    )


@router.patch("/{location_id}", response_model=LocationOut)
async def update_location(
    location_id: uuid.UUID, body: LocationUpdate, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx,
        key,
        f"location.update:{location_id}",
        body,
        lambda: service.update_location(ctx, location_id, body),
    )


stock_router = APIRouter(prefix="/w/stock", tags=["stock"])

Limit = Annotated[int, Query(ge=1, le=100)]


@stock_router.get("/balances", response_model=list[StockBalanceOut])
async def stock_balances(
    ctx: WorkspaceCtx,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    include_zero: Annotated[bool, Query()] = False,
) -> list[StockBalanceOut]:
    return await service.stock_balances(ctx, location_id=location_id, product_id=product_id, include_zero=include_zero)


@stock_router.get("/movements", response_model=list[StockMovementOut])
async def list_movements(
    ctx: WorkspaceCtx,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    before_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Limit = 50,
) -> list[StockMovementOut]:
    return await service.list_movements(
        ctx, location_id=location_id, product_id=product_id, before_id=before_id, limit=limit
    )


@stock_router.post("/opening", response_model=StockMovementOut, status_code=status.HTTP_201_CREATED)
async def record_opening(body: OpeningStockIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "stock.opening", body, lambda: service.record_opening_stock(ctx, body), status_code=201
    )


@stock_router.post("/adjustments", response_model=StockMovementOut, status_code=status.HTTP_201_CREATED)
async def adjust_stock(body: StockAdjustmentIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "stock.adjust", body, lambda: service.adjust_stock(ctx, body), status_code=201
    )


@stock_router.post(
    "/movements/{movement_id}/reverse", response_model=StockMovementOut, status_code=status.HTTP_201_CREATED
)
async def reverse_movement(
    movement_id: uuid.UUID, body: ReverseIn, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx,
        key,
        f"stock.reverse:{movement_id}",
        body,
        lambda: service.reverse_movement(ctx, movement_id, body),
        status_code=201,
    )


@stock_router.get("/transfers", response_model=list[TransferOut])
async def list_transfers(
    ctx: WorkspaceCtx, before_id: Annotated[uuid.UUID | None, Query()] = None, limit: Limit = 50
) -> list[TransferOut]:
    return await service.list_transfers(ctx, before_id=before_id, limit=limit)


@stock_router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
async def transfer_stock(body: TransferIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "stock.transfer", body, lambda: service.transfer_stock(ctx, body), status_code=201
    )


@stock_router.get("/wastage", response_model=list[WastageOut])
async def list_wastage(
    ctx: WorkspaceCtx,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    before_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Limit = 50,
) -> list[WastageOut]:
    return await service.list_wastage(ctx, location_id=location_id, before_id=before_id, limit=limit)


@stock_router.post("/wastage", response_model=WastageOut, status_code=status.HTTP_201_CREATED)
async def record_wastage(body: WastageIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "stock.wastage", body, lambda: service.record_wastage(ctx, body), status_code=201
    )
