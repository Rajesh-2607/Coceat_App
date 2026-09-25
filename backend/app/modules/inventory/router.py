import uuid

from fastapi import APIRouter, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.inventory import service
from app.modules.inventory.schemas import LocationCreate, LocationOut, LocationUpdate

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
