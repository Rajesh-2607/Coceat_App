import uuid

from fastapi import APIRouter, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.accounts.schemas import MemberIn, StaffOut, StaffUpdate
from app.modules.staff import service

router = APIRouter(prefix="/w/staff", tags=["staff"])


@router.get("", response_model=list[StaffOut])
async def list_staff(ctx: WorkspaceCtx) -> list[StaffOut]:
    return await service.list_staff(ctx)


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def add_staff(body: MemberIn, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(ctx, key, "staff.upsert", body, lambda: service.add_staff(ctx, body), status_code=201)


@router.patch("/{membership_id}", response_model=StaffOut)
async def update_staff(
    membership_id: uuid.UUID, body: StaffUpdate, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx, key, f"staff.update:{membership_id}", body, lambda: service.update_staff(ctx, membership_id, body)
    )
