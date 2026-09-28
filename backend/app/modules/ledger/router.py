import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.ledger import service
from app.modules.ledger.schemas import (
    CrateBalanceOut,
    CrateEntryIn,
    CrateLedgerEntryOut,
    PaymentIn,
    PaymentOut,
    ReverseIn,
)

router = APIRouter(prefix="/w/crates", tags=["ledger"])


@router.get("/balances", response_model=list[CrateBalanceOut])
async def crate_balances(ctx: WorkspaceCtx, all_parties: Annotated[bool, Query()] = False) -> list[CrateBalanceOut]:
    """Crates currently held by each party (only parties holding some, unless ``all_parties``)."""
    return await service.crate_balances(ctx, only_outstanding=not all_parties)


@router.post("/entries", response_model=CrateLedgerEntryOut, status_code=status.HTTP_201_CREATED)
async def record_crates(body: CrateEntryIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "crate.record", body, lambda: service.record_crates(ctx, body), status_code=201
    )


money_router = APIRouter(prefix="/w/money", tags=["money"])


@money_router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    ctx: WorkspaceCtx,
    party_id: Annotated[uuid.UUID | None, Query()] = None,
    before_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PaymentOut]:
    return await service.list_payments(ctx, party_id=party_id, before_id=before_id, limit=limit)


@money_router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(body: PaymentIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "payment.create", body, lambda: service.create_payment(ctx, body), status_code=201
    )


@money_router.post("/payments/{payment_id}/reverse", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def reverse_payment(
    payment_id: uuid.UUID, body: ReverseIn, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx,
        key,
        f"payment.reverse:{payment_id}",
        body,
        lambda: service.reverse_payment(ctx, payment_id, body.reason),
        status_code=201,
    )
