"""Units, grades, products and varieties. Nothing here is deleted: retire an item with ``is_active = false``."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import Ctx
from app.core.errors import NotFound, Unprocessable
from app.core.service_utils import flush_unique
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.catalog.models import Grade, Product, Unit, Variety
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
from app.modules.platform.modules import ModuleKey

# code, name, Tamil name, kind, base units (grams / pieces) per unit
DEFAULT_UNITS: tuple[tuple[str, str, str, str, int], ...] = (
    ("kg", "Kilogram", "கிலோ", "weight", 1_000),
    ("quintal", "Quintal (100 kg)", "குவிண்டால்", "weight", 100_000),
    ("tonne", "Tonne", "டன்", "weight", 1_000_000),
    ("piece", "Piece", "எண்ணிக்கை", "count", 1),
    ("dozen", "Dozen", "டஜன்", "count", 12),
    ("bunch", "Bunch", "கட்டு", "count", 1),
    ("crate", "Crate", "கூடை", "count", 1),
)


def _view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.CATALOG_VIEW)


def _manage(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.CATALOG_MANAGE)


def _apply(row: object, changes: dict[str, object], clearable: frozenset[str]) -> None:
    for field, value in changes.items():
        if value is None and field not in clearable:
            continue
        setattr(row, field, value)


async def seed_default_units(db: AsyncSession, business_id: uuid.UUID) -> None:
    """Called when a business is created (the tenant context is already set to it)."""
    for code, name, name_ta, kind, factor in DEFAULT_UNITS:
        db.add(Unit(business_id=business_id, code=code, name=name, name_ta=name_ta, kind=kind, base_factor=factor))
    await db.flush()


# --- units -----------------------------------------------------------------------------------------------


async def _unit(ctx: Ctx, unit_id: uuid.UUID) -> Unit:
    unit = await ctx.db.scalar(select(Unit).where(Unit.id == unit_id))
    if unit is None:
        raise NotFound("Unit not found")
    return unit


async def list_units(ctx: Ctx) -> list[UnitOut]:
    _view(ctx)
    rows = await ctx.db.scalars(select(Unit).order_by(Unit.kind, Unit.base_factor, Unit.code))
    return [UnitOut.model_validate(r) for r in rows]


async def create_unit(ctx: Ctx, data: UnitCreate) -> UnitOut:
    _manage(ctx)
    unit = Unit(**data.model_dump())
    ctx.db.add(unit)
    await flush_unique(ctx, "A unit with this code already exists", "unit_code_taken")
    await ctx.db.refresh(unit)
    out = UnitOut.model_validate(unit)
    await audit.record(ctx, "unit.create", entity_type="unit", entity_id=unit.id, after=out)
    return out


async def update_unit(ctx: Ctx, unit_id: uuid.UUID, data: UnitUpdate) -> UnitOut:
    _manage(ctx)
    unit = await _unit(ctx, unit_id)
    before = UnitOut.model_validate(unit)
    _apply(unit, data.model_dump(exclude_unset=True), frozenset({"name_ta"}))
    await ctx.db.flush()
    await ctx.db.refresh(unit)
    out = UnitOut.model_validate(unit)
    await audit.record(ctx, "unit.update", entity_type="unit", entity_id=unit.id, before=before, after=out)
    return out


# --- grades ----------------------------------------------------------------------------------------------


async def _grade(ctx: Ctx, grade_id: uuid.UUID) -> Grade:
    grade = await ctx.db.scalar(select(Grade).where(Grade.id == grade_id))
    if grade is None:
        raise NotFound("Grade not found")
    return grade


async def list_grades(ctx: Ctx) -> list[GradeOut]:
    _view(ctx)
    rows = await ctx.db.scalars(select(Grade).order_by(Grade.name))
    return [GradeOut.model_validate(r) for r in rows]


async def create_grade(ctx: Ctx, data: GradeCreate) -> GradeOut:
    _manage(ctx)
    grade = Grade(**data.model_dump())
    ctx.db.add(grade)
    await flush_unique(ctx, "A grade with this name already exists", "grade_name_taken")
    await ctx.db.refresh(grade)
    out = GradeOut.model_validate(grade)
    await audit.record(ctx, "grade.create", entity_type="grade", entity_id=grade.id, after=out)
    return out


async def update_grade(ctx: Ctx, grade_id: uuid.UUID, data: GradeUpdate) -> GradeOut:
    _manage(ctx)
    grade = await _grade(ctx, grade_id)
    before = GradeOut.model_validate(grade)
    _apply(grade, data.model_dump(exclude_unset=True), frozenset({"name_ta"}))
    await flush_unique(ctx, "A grade with this name already exists", "grade_name_taken")
    await ctx.db.refresh(grade)
    out = GradeOut.model_validate(grade)
    await audit.record(ctx, "grade.update", entity_type="grade", entity_id=grade.id, before=before, after=out)
    return out


# --- products and varieties ------------------------------------------------------------------------------


async def _product(ctx: Ctx, product_id: uuid.UUID) -> Product:
    product = await ctx.db.scalar(select(Product).where(Product.id == product_id))
    if product is None:
        raise NotFound("Product not found")
    return product


async def _product_out(ctx: Ctx, products: list[Product]) -> list[ProductOut]:
    ids = [p.id for p in products]
    by_product: dict[uuid.UUID, list[VarietyOut]] = {i: [] for i in ids}
    if ids:
        rows = await ctx.db.scalars(select(Variety).where(Variety.product_id.in_(ids)).order_by(Variety.name))
        for v in rows:
            by_product[v.product_id].append(VarietyOut.model_validate(v))
    out: list[ProductOut] = []
    for p in products:
        item = ProductOut.model_validate(p)
        item.varieties = by_product[p.id]
        out.append(item)
    return out


async def _check_unit_kind(ctx: Ctx, unit_id: uuid.UUID, kind: str) -> None:
    unit = await ctx.db.scalar(select(Unit).where(Unit.id == unit_id))
    if unit is None:
        raise Unprocessable("Unknown unit", code="unknown_unit")
    if unit.kind != kind:
        raise Unprocessable("The unit must measure the same way as the product", code="unit_kind_mismatch")


async def list_products(ctx: Ctx, *, include_inactive: bool = False) -> list[ProductOut]:
    _view(ctx)
    stmt = select(Product).order_by(Product.name)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    return await _product_out(ctx, list(await ctx.db.scalars(stmt)))


async def get_product(ctx: Ctx, product_id: uuid.UUID) -> ProductOut:
    _view(ctx)
    return (await _product_out(ctx, [await _product(ctx, product_id)]))[0]


async def create_product(ctx: Ctx, data: ProductCreate) -> ProductOut:
    _manage(ctx)
    await _check_unit_kind(ctx, data.unit_id, data.kind)
    product = Product(**data.model_dump())
    ctx.db.add(product)
    await flush_unique(ctx, "A product with this name already exists", "product_name_taken")
    await ctx.db.refresh(product)
    out = (await _product_out(ctx, [product]))[0]
    await audit.record(ctx, "product.create", entity_type="product", entity_id=product.id, after=out)
    return out


async def update_product(ctx: Ctx, product_id: uuid.UUID, data: ProductUpdate) -> ProductOut:
    _manage(ctx)
    product = await _product(ctx, product_id)
    before = (await _product_out(ctx, [product]))[0]
    changes = data.model_dump(exclude_unset=True)
    if changes.get("unit_id") is not None:
        await _check_unit_kind(ctx, changes["unit_id"], product.kind)
    _apply(product, changes, frozenset({"name_ta", "default_price_paise", "hsn_code"}))
    await flush_unique(ctx, "A product with this name already exists", "product_name_taken")
    await ctx.db.refresh(product)
    out = (await _product_out(ctx, [product]))[0]
    await audit.record(ctx, "product.update", entity_type="product", entity_id=product.id, before=before, after=out)
    return out


async def add_variety(ctx: Ctx, product_id: uuid.UUID, data: VarietyCreate) -> VarietyOut:
    _manage(ctx)
    product = await _product(ctx, product_id)
    variety = Variety(product_id=product.id, **data.model_dump())
    ctx.db.add(variety)
    await flush_unique(ctx, "This product already has a variety with this name", "variety_name_taken")
    await ctx.db.refresh(variety)
    out = VarietyOut.model_validate(variety)
    await audit.record(ctx, "variety.create", entity_type="variety", entity_id=variety.id, after=out)
    return out


async def update_variety(ctx: Ctx, product_id: uuid.UUID, variety_id: uuid.UUID, data: VarietyUpdate) -> VarietyOut:
    _manage(ctx)
    variety = await ctx.db.scalar(select(Variety).where(Variety.id == variety_id, Variety.product_id == product_id))
    if variety is None:
        raise NotFound("Variety not found")
    before = VarietyOut.model_validate(variety)
    _apply(variety, data.model_dump(exclude_unset=True), frozenset({"name_ta"}))
    await flush_unique(ctx, "This product already has a variety with this name", "variety_name_taken")
    await ctx.db.refresh(variety)
    out = VarietyOut.model_validate(variety)
    await audit.record(ctx, "variety.update", entity_type="variety", entity_id=variety.id, before=before, after=out)
    return out


# --- for other modules (stock, sales) --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StockItem:
    """A validated (product, variety, grade) triple belonging to the current business."""

    product_id: uuid.UUID
    variety_id: uuid.UUID | None
    grade_id: uuid.UUID | None
    kind: str


async def resolve_stock_item(
    ctx: Ctx, product_id: uuid.UUID, variety_id: uuid.UUID | None, grade_id: uuid.UUID | None
) -> StockItem:
    """404 if any part is missing or belongs to another business; 422 if a variety isn't this product's."""
    product = await _product(ctx, product_id)
    if not product.is_active:
        raise Unprocessable("This product is no longer active", code="product_inactive")
    if variety_id is not None:
        variety = await ctx.db.scalar(select(Variety).where(Variety.id == variety_id))
        if variety is None:
            raise NotFound("Variety not found")
        if variety.product_id != product.id:
            raise Unprocessable("This variety belongs to a different product", code="variety_mismatch")
    if grade_id is not None:
        await _grade(ctx, grade_id)
    return StockItem(product.id, variety_id, grade_id, product.kind)


async def item_labels(
    ctx: Ctx, product_ids: set[uuid.UUID], variety_ids: set[uuid.UUID], grade_ids: set[uuid.UUID]
) -> tuple[dict[uuid.UUID, Product], dict[uuid.UUID, Variety], dict[uuid.UUID, Grade]]:
    """Names for stock rows (read-only lookup used by the stock module's balance views)."""
    products = {p.id: p for p in await ctx.db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    varieties = {v.id: v for v in await ctx.db.scalars(select(Variety).where(Variety.id.in_(variety_ids)))}
    grades = {g.id: g for g in await ctx.db.scalars(select(Grade).where(Grade.id.in_(grade_ids)))}
    return products, varieties, grades


@dataclass(frozen=True, slots=True)
class SaleItem:
    """A product/variety/grade/unit as it must be printed on a bill or purchase entry."""

    stock: StockItem
    unit_id: uuid.UUID
    unit_code: str
    unit_base_factor: int
    description: str
    description_ta: str | None
    hsn_code: str | None
    gst_rate_bp: int


async def resolve_sale_item(
    ctx: Ctx, product_id: uuid.UUID, variety_id: uuid.UUID | None, grade_id: uuid.UUID | None, unit_id: uuid.UUID
) -> SaleItem:
    """Validate a line item and its unit (404 for foreign ids, 422 for the wrong kind of unit); snapshot its names."""
    stock = await resolve_stock_item(ctx, product_id, variety_id, grade_id)
    product = await _product(ctx, product_id)
    unit = await ctx.db.scalar(select(Unit).where(Unit.id == unit_id))
    if unit is None:
        raise Unprocessable("Unknown unit", code="unknown_unit")
    if unit.kind != product.kind or not unit.is_active:
        raise Unprocessable("The unit must measure the same way as the product", code="unit_kind_mismatch")
    parts_en = [product.name]
    parts_ta = [product.name_ta or product.name]
    if variety_id is not None:
        variety = await ctx.db.scalar(select(Variety).where(Variety.id == variety_id))
        assert variety is not None  # resolve_stock_item already checked it
        parts_en.append(variety.name)
        parts_ta.append(variety.name_ta or variety.name)
    if grade_id is not None:
        grade = await ctx.db.scalar(select(Grade).where(Grade.id == grade_id))
        assert grade is not None
        parts_en.append(grade.name)
        parts_ta.append(grade.name_ta or grade.name)
    return SaleItem(
        stock=stock,
        unit_id=unit.id,
        unit_code=unit.code,
        unit_base_factor=unit.base_factor,
        description=" · ".join(parts_en),
        description_ta=" · ".join(parts_ta),
        hsn_code=product.hsn_code,
        gst_rate_bp=product.gst_rate_bp,
    )
