import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.purchases import service
from app.modules.purchases.schemas import PurchaseIn, PurchaseOut, PurchaseSummaryOut, VoidIn

router = APIRouter(prefix="/w/purchases", tags=["purchases"])


@router.get("", response_model=list[PurchaseSummaryOut])
async def list_purchases(
    ctx: WorkspaceCtx,
    q: Annotated[str | None, Query(max_length=60)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    before_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PurchaseSummaryOut]:
    return await service.list_purchases(
        ctx, q=q, date_from=date_from, date_to=date_to, supplier_id=supplier_id, before_id=before_id, limit=limit
    )


@router.post("", response_model=PurchaseOut, status_code=status.HTTP_201_CREATED)
async def create_purchase(body: PurchaseIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "purchase.create", body, lambda: service.create_purchase(ctx, body), status_code=201
    )


@router.get("/{purchase_id}", response_model=PurchaseOut)
async def get_purchase(purchase_id: uuid.UUID, ctx: WorkspaceCtx) -> PurchaseOut:
    return await service.get_purchase(ctx, purchase_id)


@router.post("/{purchase_id}/void", response_model=PurchaseOut)
async def void_purchase(purchase_id: uuid.UUID, body: VoidIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, f"purchase.void:{purchase_id}", body, lambda: service.void_purchase(ctx, purchase_id, body)
    )
