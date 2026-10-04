"""Buy / Receive: stock coming in from a supplier, with what was paid now and what is still owed.

Like a sale, one purchase is one transaction: number, entry, lines, stock movements, supplier-ledger entries,
payments and audit event.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select

from app.core.context import Ctx
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.ids import uuid7
from app.core.numbering import next_number
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.inventory import service as inventory
from app.modules.ledger import service as ledger
from app.modules.ledger.models import Payment
from app.modules.parties import service as parties
from app.modules.platform.modules import ModuleKey
from app.modules.purchases.models import Purchase, PurchaseLine
from app.modules.purchases.schemas import (
    PurchaseIn,
    PurchaseLineOut,
    PurchaseOut,
    PurchasePaymentOut,
    PurchaseSummaryOut,
    VoidIn,
)
from app.modules.sales.pricing import line_amount
from app.modules.sales.service import today_ist

PURCHASE_SERIES = "P"


def _view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.BUY)
    require_permission(ctx, Perm.PURCHASES_VIEW)


async def _purchase(ctx: Ctx, purchase_id: uuid.UUID) -> Purchase:
    purchase = await ctx.db.scalar(select(Purchase).where(Purchase.id == purchase_id))
    if purchase is None or not ctx.can_access_location(purchase.location_id):
        raise NotFound("Purchase not found")
    return purchase


async def _out(ctx: Ctx, purchase: Purchase) -> PurchaseOut:
    lines = await ctx.db.scalars(
        select(PurchaseLine).where(PurchaseLine.purchase_id == purchase.id).order_by(PurchaseLine.line_no)
    )
    payments = await ctx.db.scalars(
        select(Payment)
        .where(Payment.reference_type == "purchase", Payment.reference_id == str(purchase.id))
        .order_by(Payment.id)
    )
    out = PurchaseOut.model_validate(purchase)
    out.credit_paise = purchase.total_paise - purchase.paid_paise
    out.lines = [PurchaseLineOut.model_validate(ln) for ln in lines]
    out.payments = [PurchasePaymentOut.model_validate(p) for p in payments]
    return out


async def get_purchase(ctx: Ctx, purchase_id: uuid.UUID) -> PurchaseOut:
    _view(ctx)
    return await _out(ctx, await _purchase(ctx, purchase_id))


async def list_purchases(
    ctx: Ctx,
    *,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    supplier_id: uuid.UUID | None,
    before_id: uuid.UUID | None,
    limit: int,
) -> list[PurchaseSummaryOut]:
    _view(ctx)
    stmt = select(Purchase).order_by(Purchase.id.desc()).limit(limit)
    if ctx.tenant.location_ids is not None:
        stmt = stmt.where(Purchase.location_id.in_(ctx.tenant.location_ids))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Purchase.purchase_number.ilike(like),
                Purchase.supplier_name.ilike(like),
                Purchase.supplier_bill_no.ilike(like),
            )
        )
    if date_from is not None:
        stmt = stmt.where(Purchase.purchase_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Purchase.purchase_date <= date_to)
    if supplier_id is not None:
        stmt = stmt.where(Purchase.supplier_id == supplier_id)
    if before_id is not None:
        stmt = stmt.where(Purchase.id < before_id)
    return [PurchaseSummaryOut.model_validate(p) for p in await ctx.db.scalars(stmt)]


async def create_purchase(ctx: Ctx, data: PurchaseIn) -> PurchaseOut:
    require_module(ctx, ModuleKey.BUY)
    require_permission(ctx, Perm.PURCHASES_CREATE)
    await inventory.require_location(ctx, data.location_id)
    supplier = await parties.party_for_document(ctx, "supplier", data.supplier_id)
    day = today_ist()
    if data.purchase_date is not None and data.purchase_date > day:
        raise Unprocessable("The purchase date cannot be in the future", code="future_date")
    on_date = data.purchase_date or day

    items = [
        await catalog.resolve_sale_item(ctx, ln.product_id, ln.variety_id, ln.grade_id, ln.unit_id) for ln in data.lines
    ]
    amounts = [
        line_amount(ln.quantity, item.unit_base_factor, ln.unit_cost_paise)
        for ln, item in zip(data.lines, items, strict=True)
    ]
    total = sum(amounts)
    if total <= 0:
        raise Unprocessable("A purchase needs a total above zero", code="zero_total")
    paid = sum(p.amount_paise for p in data.payments)
    if paid > total:
        raise Unprocessable("Payments are more than the purchase total", code="overpaid")

    number, fy, seq = await next_number(ctx, PURCHASE_SERIES, on_date)
    purchase = Purchase(
        id=uuid7(),
        series=PURCHASE_SERIES,
        fy=fy,
        seq=seq,
        purchase_number=number,
        purchase_date=on_date,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        location_id=data.location_id,
        supplier_bill_no=data.supplier_bill_no,
        total_paise=total,
        paid_paise=paid,
        status="active",
        note=data.note,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(purchase)
    await ctx.db.flush()
    for i, (ln, item, amount) in enumerate(zip(data.lines, items, amounts, strict=True), start=1):
        ctx.db.add(
            PurchaseLine(
                purchase_id=purchase.id,
                line_no=i,
                product_id=item.stock.product_id,
                variety_id=item.stock.variety_id,
                grade_id=item.stock.grade_id,
                unit_id=item.unit_id,
                description=item.description,
                description_ta=item.description_ta,
                unit_code=item.unit_code,
                unit_base_factor=item.unit_base_factor,
                quantity_base=ln.quantity,
                unit_cost_paise=ln.unit_cost_paise,
                amount_paise=amount,
            )
        )
    await ctx.db.flush()

    for ln, item in zip(data.lines, items, strict=True):
        await inventory.post_document_movement(
            ctx,
            data.location_id,
            item.stock,
            ln.quantity,
            "purchase",
            reference_type="purchase",
            reference_id=str(purchase.id),
            reason=number,
        )
    # we now owe the supplier the whole amount (negative), then payments made bring it back towards zero
    await ledger.post_party_entry(
        ctx, supplier.id, "purchase", -total, note=number, reference_type="purchase", reference_id=str(purchase.id)
    )
    for pay in data.payments:
        await ledger.record_payment(
            ctx,
            party_id=supplier.id,
            direction="out",
            method=pay.method,
            amount_paise=pay.amount_paise,
            reference_type="purchase",
            reference_id=str(purchase.id),
            note=number,
        )

    await ctx.db.refresh(purchase)
    out = await _out(ctx, purchase)
    await audit.record(ctx, "purchase.create", entity_type="purchase", entity_id=purchase.id, after=out)
    return out


async def void_purchase(ctx: Ctx, purchase_id: uuid.UUID, data: VoidIn) -> PurchaseOut:
    """Cancel a purchase entry. Refused if the goods have already been sold (there is no stock to take back)."""
    require_module(ctx, ModuleKey.BUY)
    require_permission(ctx, Perm.PURCHASES_VOID)
    purchase = await _purchase(ctx, purchase_id)
    if purchase.status == "void":
        raise Conflict("This purchase is already cancelled", code="already_void")
    before = await _out(ctx, purchase)
    ref = str(purchase.id)
    await inventory.reverse_document_movements(ctx, "purchase", ref, data.reason)
    await ledger.reverse_document(ctx, "purchase", ref, data.reason)
    purchase.status = "void"
    purchase.void_reason = data.reason
    purchase.voided_at = datetime.now(UTC)
    purchase.voided_by = ctx.actor.user_id
    await ctx.db.flush()
    await ctx.db.refresh(purchase)
    out = await _out(ctx, purchase)
    await audit.record(ctx, "purchase.void", entity_type="purchase", entity_id=purchase.id, before=before, after=out)
    return out


async def purchase_totals(ctx: Ctx, date_from: date, date_to: date) -> dict[str, int]:
    _view(ctx)
    row = (
        await ctx.db.execute(
            select(
                func.count(Purchase.id),
                func.coalesce(func.sum(Purchase.total_paise), 0),
                func.coalesce(func.sum(Purchase.paid_paise), 0),
            ).where(Purchase.status == "active", Purchase.purchase_date >= date_from, Purchase.purchase_date <= date_to)
        )
    ).one()
    return {"purchases": int(row[0]), "total_paise": int(row[1]), "paid_paise": int(row[2])}
