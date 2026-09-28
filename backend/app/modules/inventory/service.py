import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.context import Ctx
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.ids import uuid7
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.inventory.models import Location, StockMovement, StockTransfer, WastageEntry
from app.modules.inventory.schemas import (
    LocationCreate,
    LocationOut,
    LocationUpdate,
    OpeningStockIn,
    ReverseIn,
    StockAdjustmentIn,
    StockBalanceOut,
    StockItemIn,
    StockMovementOut,
    TransferIn,
    TransferOut,
    WastageIn,
    WastageOut,
)
from app.modules.platform.modules import ModuleKey


async def _get(ctx: Ctx, location_id: uuid.UUID) -> Location:
    # tenant criteria + RLS make another business's row indistinguishable from a missing one
    location = await ctx.db.scalar(select(Location).where(Location.id == location_id))
    if location is None or not ctx.can_access_location(location.id):
        raise NotFound("Location not found")
    return location


async def require_location(ctx: Ctx, location_id: uuid.UUID) -> Location:
    """For other modules: the location exists in this business and the member may act on it (else 404)."""
    return await _get(ctx, location_id)


async def list_locations(ctx: Ctx) -> list[LocationOut]:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_VIEW)
    rows = await ctx.db.scalars(select(Location).order_by(Location.name))
    return [LocationOut.model_validate(r) for r in rows if ctx.can_access_location(r.id)]


async def get_location(ctx: Ctx, location_id: uuid.UUID) -> LocationOut:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_VIEW)
    return LocationOut.model_validate(await _get(ctx, location_id))


async def _flush_unique(ctx: Ctx) -> None:
    try:
        async with ctx.db.begin_nested():
            await ctx.db.flush()
    except IntegrityError as exc:
        raise Conflict("A location with this name already exists", code="location_name_taken") from exc


async def create_location(ctx: Ctx, data: LocationCreate) -> LocationOut:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_MANAGE)
    location = Location(**data.model_dump())
    ctx.db.add(location)
    await _flush_unique(ctx)
    await ctx.db.refresh(location)
    out = LocationOut.model_validate(location)
    await audit.record(ctx, "location.create", entity_type="location", entity_id=location.id, after=out)
    return out


async def update_location(ctx: Ctx, location_id: uuid.UUID, data: LocationUpdate) -> LocationOut:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_MANAGE)
    location = await _get(ctx, location_id)
    before = LocationOut.model_validate(location)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field != "name_ta":
            continue  # only name_ta is clearable
        setattr(location, field, value)
    await _flush_unique(ctx)
    await ctx.db.refresh(location)
    out = LocationOut.model_validate(location)
    await audit.record(ctx, "location.update", entity_type="location", entity_id=location.id, before=before, after=out)
    return out


# --- stock -----------------------------------------------------------------------------------------------


def _stock_view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.STOCK_VIEW)


def _stock_move(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.STOCK_MOVE)


def _movement_out(m: StockMovement) -> StockMovementOut:
    return StockMovementOut.model_validate(m)


async def _lock_item(ctx: Ctx, location_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """Serialize concurrent stock-outs of one product at one location (released when the transaction ends)."""
    key = f"{ctx.tenant.business_id}:{location_id}:{product_id}"
    await ctx.db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key})


async def _balance(
    ctx: Ctx, location_id: uuid.UUID, product_id: uuid.UUID, variety_id: uuid.UUID | None, grade_id: uuid.UUID | None
) -> int:
    total = await ctx.db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
            StockMovement.location_id == location_id,
            StockMovement.product_id == product_id,
            StockMovement.variety_id.is_not_distinct_from(variety_id),
            StockMovement.grade_id.is_not_distinct_from(grade_id),
        )
    )
    return int(total or 0)


async def _add_movement(
    ctx: Ctx,
    location_id: uuid.UUID,
    item: catalog.StockItem,
    quantity: int,
    movement_type: str,
    *,
    reason: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
    reversal_of: uuid.UUID | None = None,
) -> StockMovement:
    """Append one movement. Stock going out is checked against the balance under a per-item lock."""
    if quantity < 0:
        await _lock_item(ctx, location_id, item.product_id)
        if await _balance(ctx, location_id, item.product_id, item.variety_id, item.grade_id) + quantity < 0:
            raise Unprocessable("Not enough stock at this location", code="insufficient_stock")
    movement = StockMovement(
        id=uuid7(),
        location_id=location_id,
        product_id=item.product_id,
        variety_id=item.variety_id,
        grade_id=item.grade_id,
        quantity=quantity,
        movement_type=movement_type,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        reversal_of=reversal_of,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(movement)
    await ctx.db.flush()
    await ctx.db.refresh(movement)
    return movement


async def _prepare(ctx: Ctx, location_id: uuid.UUID, item: StockItemIn) -> catalog.StockItem:
    await require_location(ctx, location_id)
    return await catalog.resolve_stock_item(ctx, item.product_id, item.variety_id, item.grade_id)


async def record_opening_stock(ctx: Ctx, data: OpeningStockIn) -> StockMovementOut:
    _stock_move(ctx)
    item = await _prepare(ctx, data.location_id, data)
    movement = await _add_movement(ctx, data.location_id, item, data.quantity, "opening", reason=data.note)
    out = _movement_out(movement)
    await audit.record(ctx, "stock.opening", entity_type="stock_movement", entity_id=movement.id, after=out)
    return out


async def adjust_stock(ctx: Ctx, data: StockAdjustmentIn) -> StockMovementOut:
    _stock_move(ctx)
    if data.quantity == 0:
        raise Unprocessable("Adjustment cannot be zero", code="zero_adjustment")
    item = await _prepare(ctx, data.location_id, data)
    movement = await _add_movement(ctx, data.location_id, item, data.quantity, "adjustment", reason=data.reason)
    out = _movement_out(movement)
    await audit.record(ctx, "stock.adjust", entity_type="stock_movement", entity_id=movement.id, after=out)
    return out


async def transfer_stock(ctx: Ctx, data: TransferIn) -> TransferOut:
    _stock_move(ctx)
    if data.from_location_id == data.to_location_id:
        raise Unprocessable("Choose two different locations", code="same_location")
    await require_location(ctx, data.from_location_id)
    await require_location(ctx, data.to_location_id)
    lines = sorted(data.lines, key=lambda line: str(line.product_id))  # stable lock order: no deadlocks
    resolved = [(await catalog.resolve_stock_item(ctx, ln.product_id, ln.variety_id, ln.grade_id), ln) for ln in lines]

    transfer = StockTransfer(
        from_location_id=data.from_location_id,
        to_location_id=data.to_location_id,
        note=data.note,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(transfer)
    await ctx.db.flush()
    movements: list[StockMovement] = []
    for item, line in resolved:
        ref = str(transfer.id)
        out_move = await _add_movement(
            ctx,
            data.from_location_id,
            item,
            -line.quantity,
            "transfer_out",
            reference_type="transfer",
            reference_id=ref,
        )
        in_move = await _add_movement(
            ctx, data.to_location_id, item, line.quantity, "transfer_in", reference_type="transfer", reference_id=ref
        )
        movements += [out_move, in_move]
    await ctx.db.refresh(transfer)
    out = _transfer_out(transfer, [_movement_out(m) for m in movements])
    await audit.record(ctx, "stock.transfer", entity_type="stock_transfer", entity_id=transfer.id, after=out)
    return out


def _transfer_out(t: StockTransfer, movements: list[StockMovementOut]) -> TransferOut:
    return TransferOut(
        id=t.id,
        from_location_id=t.from_location_id,
        to_location_id=t.to_location_id,
        note=t.note,
        created_by=t.created_by,
        created_at=t.created_at,
        movements=movements,
    )


def _wastage_out(w: WastageEntry, *, reversed_ids: set[uuid.UUID]) -> WastageOut:
    return WastageOut(
        id=w.id,
        location_id=w.location_id,
        product_id=w.product_id,
        variety_id=w.variety_id,
        grade_id=w.grade_id,
        quantity=w.quantity,
        reason_code=w.reason_code,
        note=w.note,
        movement_id=w.movement_id,
        reversed=w.movement_id in reversed_ids,
        created_by=w.created_by,
        created_at=w.created_at,
    )


async def record_wastage(ctx: Ctx, data: WastageIn) -> WastageOut:
    _stock_move(ctx)
    item = await _prepare(ctx, data.location_id, data)
    wastage_id = uuid7()
    movement = await _add_movement(
        ctx,
        data.location_id,
        item,
        -data.quantity,
        "wastage",
        reason=data.note or data.reason_code,
        reference_type="wastage",
        reference_id=str(wastage_id),
    )
    entry = WastageEntry(
        id=wastage_id,
        location_id=data.location_id,
        product_id=item.product_id,
        variety_id=item.variety_id,
        grade_id=item.grade_id,
        quantity=data.quantity,
        reason_code=data.reason_code,
        note=data.note,
        movement_id=movement.id,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(entry)
    await ctx.db.flush()
    await ctx.db.refresh(entry)
    out = _wastage_out(entry, reversed_ids=set())
    await audit.record(ctx, "stock.wastage", entity_type="wastage_entry", entity_id=entry.id, after=out)
    return out


REVERSIBLE = frozenset({"opening", "adjustment", "wastage"})


async def reverse_movement(ctx: Ctx, movement_id: uuid.UUID, data: ReverseIn) -> StockMovementOut:
    """Undo an opening, adjustment or wastage entry with an equal and opposite movement."""
    _stock_move(ctx)
    original = await ctx.db.scalar(select(StockMovement).where(StockMovement.id == movement_id))
    if original is None or not ctx.can_access_location(original.location_id):
        raise NotFound("Stock movement not found")
    if original.movement_type not in REVERSIBLE:
        raise Unprocessable("This kind of movement cannot be reversed", code="not_reversible")
    already = await ctx.db.scalar(select(StockMovement.id).where(StockMovement.reversal_of == original.id))
    if already is not None:
        raise Conflict("This movement was already reversed", code="already_reversed")
    item = catalog.StockItem(original.product_id, original.variety_id, original.grade_id, kind="")
    movement = await _add_movement(
        ctx,
        original.location_id,
        item,
        -original.quantity,
        "reversal",
        reason=data.reason,
        reference_type=original.reference_type,
        reference_id=original.reference_id,
        reversal_of=original.id,
    )
    out = _movement_out(movement)
    await audit.record(ctx, "stock.reverse", entity_type="stock_movement", entity_id=movement.id, after=out)
    return out


# --- stock views -----------------------------------------------------------------------------------------


def _visible(ctx: Ctx, stmt: Any, column: Any) -> Any:
    """Restrict a query to the locations this member may see."""
    if ctx.tenant.location_ids is not None:
        stmt = stmt.where(column.in_(ctx.tenant.location_ids))
    return stmt


async def stock_balances(
    ctx: Ctx, *, location_id: uuid.UUID | None, product_id: uuid.UUID | None, include_zero: bool
) -> list[StockBalanceOut]:
    _stock_view(ctx)
    total = func.sum(StockMovement.quantity)
    stmt = select(
        StockMovement.location_id,
        StockMovement.product_id,
        StockMovement.variety_id,
        StockMovement.grade_id,
        total,
    ).group_by(StockMovement.location_id, StockMovement.product_id, StockMovement.variety_id, StockMovement.grade_id)
    stmt = _visible(ctx, stmt, StockMovement.location_id)
    if location_id is not None:
        stmt = stmt.where(StockMovement.location_id == location_id)
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if not include_zero:
        stmt = stmt.having(total != 0)
    rows = list((await ctx.db.execute(stmt)).all())
    products, varieties, grades = await catalog.item_labels(
        ctx,
        {r[1] for r in rows},
        {r[2] for r in rows if r[2] is not None},
        {r[3] for r in rows if r[3] is not None},
    )
    out: list[StockBalanceOut] = []
    for loc, pid, vid, gid, qty in rows:
        p = products[pid]
        v = varieties.get(vid) if vid else None
        g = grades.get(gid) if gid else None
        out.append(
            StockBalanceOut(
                location_id=loc,
                product_id=pid,
                variety_id=vid,
                grade_id=gid,
                quantity=int(qty),
                kind=p.kind,
                product_name=p.name,
                product_name_ta=p.name_ta,
                variety_name=v.name if v else None,
                variety_name_ta=v.name_ta if v else None,
                grade_name=g.name if g else None,
                grade_name_ta=g.name_ta if g else None,
            )
        )
    out.sort(key=lambda b: (b.product_name, b.variety_name or "", b.grade_name or ""))
    return out


async def list_movements(
    ctx: Ctx,
    *,
    location_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    before_id: uuid.UUID | None,
    limit: int,
) -> list[StockMovementOut]:
    _stock_view(ctx)
    stmt = select(StockMovement).order_by(StockMovement.id.desc()).limit(limit)
    stmt = _visible(ctx, stmt, StockMovement.location_id)
    if location_id is not None:
        stmt = stmt.where(StockMovement.location_id == location_id)
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if before_id is not None:
        stmt = stmt.where(StockMovement.id < before_id)
    return [_movement_out(m) for m in await ctx.db.scalars(stmt)]


async def list_transfers(ctx: Ctx, *, before_id: uuid.UUID | None, limit: int) -> list[TransferOut]:
    _stock_view(ctx)
    stmt = select(StockTransfer).order_by(StockTransfer.id.desc()).limit(limit)
    if ctx.tenant.location_ids is not None:
        allowed = ctx.tenant.location_ids
        stmt = stmt.where(StockTransfer.from_location_id.in_(allowed) | StockTransfer.to_location_id.in_(allowed))
    if before_id is not None:
        stmt = stmt.where(StockTransfer.id < before_id)
    transfers = list(await ctx.db.scalars(stmt))
    ids = [str(t.id) for t in transfers]
    by_ref: dict[str, list[StockMovementOut]] = {i: [] for i in ids}
    if ids:
        rows = await ctx.db.scalars(
            select(StockMovement)
            .where(StockMovement.reference_type == "transfer", StockMovement.reference_id.in_(ids))
            .order_by(StockMovement.id)
        )
        for m in rows:
            if m.reference_id is not None:
                by_ref[m.reference_id].append(_movement_out(m))
    return [_transfer_out(t, by_ref[str(t.id)]) for t in transfers]


async def list_wastage(
    ctx: Ctx, *, location_id: uuid.UUID | None, before_id: uuid.UUID | None, limit: int
) -> list[WastageOut]:
    _stock_view(ctx)
    stmt = select(WastageEntry).order_by(WastageEntry.id.desc()).limit(limit)
    stmt = _visible(ctx, stmt, WastageEntry.location_id)
    if location_id is not None:
        stmt = stmt.where(WastageEntry.location_id == location_id)
    if before_id is not None:
        stmt = stmt.where(WastageEntry.id < before_id)
    rows = list(await ctx.db.scalars(stmt))
    movement_ids = [w.movement_id for w in rows]
    reversed_ids: set[uuid.UUID] = set()
    if movement_ids:
        found = await ctx.db.scalars(
            select(StockMovement.reversal_of).where(StockMovement.reversal_of.in_(movement_ids))
        )
        reversed_ids = {r for r in found if r is not None}
    return [_wastage_out(w, reversed_ids=reversed_ids) for w in rows]


async def stock_counts(ctx: Ctx) -> tuple[int, int]:
    """(items in stock, items below zero) across the member's locations, for the Home page. Read-only."""
    _stock_view(ctx)
    total = func.sum(StockMovement.quantity)
    stmt = select(total).group_by(
        StockMovement.location_id, StockMovement.product_id, StockMovement.variety_id, StockMovement.grade_id
    )
    stmt = _visible(ctx, stmt, StockMovement.location_id)
    sums = [int(s) for s in await ctx.db.scalars(stmt)]
    return sum(1 for s in sums if s > 0), sum(1 for s in sums if s < 0)


# --- for other modules' documents (sales, purchases) -----------------------------------------------------


async def post_document_movement(
    ctx: Ctx,
    location_id: uuid.UUID,
    item: catalog.StockItem,
    quantity: int,
    movement_type: str,
    *,
    reference_type: str,
    reference_id: str,
    reason: str | None = None,
) -> None:
    """Stock in or out for a bill, return or purchase. Going below zero is refused (insufficient_stock)."""
    await require_location(ctx, location_id)
    await _add_movement(
        ctx,
        location_id,
        item,
        quantity,
        movement_type,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
    )


async def reverse_document_movements(ctx: Ctx, reference_type: str, reference_id: str, reason: str) -> None:
    """Undo every not-yet-reversed movement of a document (a voided bill or purchase)."""
    reversed_ids = select(StockMovement.reversal_of).where(StockMovement.reversal_of.is_not(None))
    rows = await ctx.db.scalars(
        select(StockMovement)
        .where(
            StockMovement.reference_type == reference_type,
            StockMovement.reference_id == reference_id,
            StockMovement.reversal_of.is_(None),
            StockMovement.id.not_in(reversed_ids),
        )
        .order_by(StockMovement.id)
    )
    for original in list(rows):
        item = catalog.StockItem(original.product_id, original.variety_id, original.grade_id, kind="")
        await _add_movement(
            ctx,
            original.location_id,
            item,
            -original.quantity,
            "reversal",
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            reversal_of=original.id,
        )


async def wastage_summary(ctx: Ctx, start: datetime, end: datetime) -> list[dict[str, int | str]]:
    """Wastage in [start, end) by reason and product, leaving out entries that were reversed."""
    _stock_view(ctx)
    reversed_ids = select(StockMovement.reversal_of).where(StockMovement.reversal_of.is_not(None))
    total = func.sum(WastageEntry.quantity)
    stmt = (
        select(WastageEntry.reason_code, WastageEntry.product_id, total)
        .where(
            WastageEntry.created_at >= start,
            WastageEntry.created_at < end,
            WastageEntry.movement_id.not_in(reversed_ids),
        )
        .group_by(WastageEntry.reason_code, WastageEntry.product_id)
        .order_by(total.desc())
    )
    stmt = _visible(ctx, stmt, WastageEntry.location_id)
    return [
        {"reason_code": reason, "product_id": str(pid), "quantity_base": int(qty)}
        for reason, pid, qty in await ctx.db.execute(stmt)
    ]
