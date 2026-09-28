import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from starlette.responses import JSONResponse

from app.core.deps import IdempotencyKey, WorkspaceCtx
from app.core.idempotency import run_idempotent
from app.modules.catalog import service
from app.modules.catalog.schemas import (
    GradeCreate,
    GradeOut,
    GradeUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    UnitCreate,
    UnitOut,
    UnitUpdate,
    VarietyCreate,
    VarietyOut,
    VarietyUpdate,
)

router = APIRouter(prefix="/w", tags=["catalog"])


# units
@router.get("/units", response_model=list[UnitOut])
async def list_units(ctx: WorkspaceCtx) -> list[UnitOut]:
    return await service.list_units(ctx)


@router.post("/units", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
async def create_unit(body: UnitCreate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(ctx, key, "unit.create", body, lambda: service.create_unit(ctx, body), status_code=201)


@router.patch("/units/{unit_id}", response_model=UnitOut)
async def update_unit(unit_id: uuid.UUID, body: UnitUpdate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, f"unit.update:{unit_id}", body, lambda: service.update_unit(ctx, unit_id, body)
    )


# grades
@router.get("/grades", response_model=list[GradeOut])
async def list_grades(ctx: WorkspaceCtx) -> list[GradeOut]:
    return await service.list_grades(ctx)


@router.post("/grades", response_model=GradeOut, status_code=status.HTTP_201_CREATED)
async def create_grade(body: GradeCreate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "grade.create", body, lambda: service.create_grade(ctx, body), status_code=201
    )


@router.patch("/grades/{grade_id}", response_model=GradeOut)
async def update_grade(grade_id: uuid.UUID, body: GradeUpdate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, f"grade.update:{grade_id}", body, lambda: service.update_grade(ctx, grade_id, body)
    )


# products and varieties
@router.get("/products", response_model=list[ProductOut])
async def list_products(ctx: WorkspaceCtx, include_inactive: Annotated[bool, Query()] = False) -> list[ProductOut]:
    return await service.list_products(ctx, include_inactive=include_inactive)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(body: ProductCreate, ctx: WorkspaceCtx, key: IdempotencyKey) -> JSONResponse:
    return await run_idempotent(
        ctx, key, "product.create", body, lambda: service.create_product(ctx, body), status_code=201
    )


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: uuid.UUID, ctx: WorkspaceCtx) -> ProductOut:
    return await service.get_product(ctx, product_id)


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID, body: ProductUpdate, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx, key, f"product.update:{product_id}", body, lambda: service.update_product(ctx, product_id, body)
    )


@router.post("/products/{product_id}/varieties", response_model=VarietyOut, status_code=status.HTTP_201_CREATED)
async def add_variety(
    product_id: uuid.UUID, body: VarietyCreate, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx,
        key,
        f"variety.create:{product_id}",
        body,
        lambda: service.add_variety(ctx, product_id, body),
        status_code=201,
    )


@router.patch("/products/{product_id}/varieties/{variety_id}", response_model=VarietyOut)
async def update_variety(
    product_id: uuid.UUID, variety_id: uuid.UUID, body: VarietyUpdate, ctx: WorkspaceCtx, key: IdempotencyKey
) -> JSONResponse:
    return await run_idempotent(
        ctx,
        key,
        f"variety.update:{variety_id}",
        body,
        lambda: service.update_variety(ctx, product_id, variety_id, body),
    )
