import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.ledger.schemas import (
    CrateAdjustmentIn,
    CrateLedgerEntryOut,
    PartyAdjustmentIn,
    PartyLedgerEntryOut,
)
from app.modules.parties import service
from app.modules.parties.schemas import PartyCreate, PartyKind, PartyOut, PartyUpdate


def _party_router(kind: PartyKind, prefix: str) -> APIRouter:
    """Customers and suppliers share behaviour; only the URL prefix, kind and module gate differ."""
    r = APIRouter(prefix=prefix, tags=[prefix.removeprefix("/w/")])

    @r.get("", response_model=list[PartyOut])
    async def list_parties(
        ctx: WorkspaceCtx,
        q: Annotated[str | None, Query(max_length=60)] = None,
        include_inactive: Annotated[bool, Query()] = False,
    ) -> list[PartyOut]:
        return await service.list_parties(ctx, kind, q=q, include_inactive=include_inactive)

    @r.post("", response_model=PartyOut, status_code=status.HTTP_201_CREATED)
    async def create_party(body: PartyCreate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
        return await run_idempotent(
            ctx, key, f"{kind}.create", body, lambda: service.create_party(ctx, kind, body), status_code=201
        )

    @r.get("/{party_id}", response_model=PartyOut)
    async def get_party(party_id: uuid.UUID, ctx: WorkspaceCtx) -> PartyOut:
        return await service.get_party(ctx, kind, party_id)

    @r.patch("/{party_id}", response_model=PartyOut)
    async def update_party(
        party_id: uuid.UUID, body: PartyUpdate, ctx: WorkspaceCtx, key: IdempotencyKey
    ) -> JSONResponse:
        return await run_idempotent(
            ctx, key, f"{kind}.update:{party_id}", body, lambda: service.update_party(ctx, kind, party_id, body)
        )

    @r.get("/{party_id}/ledger", response_model=list[PartyLedgerEntryOut])
    async def party_ledger(
        party_id: uuid.UUID,
        ctx: WorkspaceCtx,
        before_id: Annotated[uuid.UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[PartyLedgerEntryOut]:
        return await service.party_ledger(ctx, kind, party_id, before_id=before_id, limit=limit)

    @r.post("/{party_id}/adjustments", response_model=PartyLedgerEntryOut, status_code=status.HTTP_201_CREATED)
    async def adjust_balance(
        party_id: uuid.UUID, body: PartyAdjustmentIn, ctx: WorkspaceCtx, key: IdempotencyKey
    ) -> JSONResponse:
        return await run_idempotent(
            ctx,
            key,
            f"{kind}.adjust:{party_id}",
            body,
            lambda: service.adjust_balance(ctx, kind, party_id, body),
            status_code=201,
        )

    @r.get("/{party_id}/crates", response_model=list[CrateLedgerEntryOut])
    async def party_crates(
        party_id: uuid.UUID,
        ctx: WorkspaceCtx,
        before_id: Annotated[uuid.UUID | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[CrateLedgerEntryOut]:
        return await service.party_crates(ctx, kind, party_id, before_id=before_id, limit=limit)

    @r.post("/{party_id}/crate-adjustments", response_model=CrateLedgerEntryOut, status_code=status.HTTP_201_CREATED)
    async def adjust_crates(
        party_id: uuid.UUID, body: CrateAdjustmentIn, ctx: WorkspaceCtx, key: IdempotencyKey
    ) -> JSONResponse:
        return await run_idempotent(
            ctx,
            key,
            f"{kind}.crate_adjust:{party_id}",
            body,
            lambda: service.adjust_party_crates(ctx, kind, party_id, body),
            status_code=201,
        )

    return r


customers_router = _party_router("customer", "/w/customers")
suppliers_router = _party_router("supplier", "/w/suppliers")
