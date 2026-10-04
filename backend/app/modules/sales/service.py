"""Sale bills, returns (credit notes) and cancellations.

One bill is ONE database transaction: number, bill, lines, stock movements, party-ledger entries, payments and
audit events all commit together or not at all. Nothing here commits: the router does, once, via ``run_idempotent``.
"""

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

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
from app.modules.platform import service as platform
from app.modules.platform.modules import ModuleKey
from app.modules.sales.models import Bill, BillLine, SaleReturn, SaleReturnLine
from app.modules.sales.pricing import LineInput, LineResult, bill_totals, price_line
from app.modules.sales.schemas import (
    BillLineOut,
    BillOut,
    BillPaymentOut,
    BillSummaryOut,
    ReturnIn,
    ReturnLineOut,
    ReturnOut,
    SaleIn,
    VoidIn,
)

IST = ZoneInfo("Asia/Kolkata")
SALE_SERIES = "S"
RETURN_SERIES = "R"


def today_ist() -> date:
    return datetime.now(IST).date()


def _view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.BILLS)
    require_permission(ctx, Perm.BILLS_VIEW)


def _gst_state(gstin: str | None) -> str | None:
    return gstin[:2] if gstin else None


# --- reading ---------------------------------------------------------------------------------------------


async def _bill(ctx: Ctx, bill_id: uuid.UUID) -> Bill:
    bill = await ctx.db.scalar(select(Bill).where(Bill.id == bill_id))
    if bill is None or not ctx.can_access_location(bill.location_id):
        raise NotFound("Bill not found")
    return bill


async def _bill_out(ctx: Ctx, bill: Bill) -> BillOut:
    lines = list(await ctx.db.scalars(select(BillLine).where(BillLine.bill_id == bill.id).order_by(BillLine.line_no)))
    returned = dict(
        (
            await ctx.db.execute(
                select(SaleReturnLine.bill_line_id, func.sum(SaleReturnLine.quantity_base))
                .where(SaleReturnLine.bill_line_id.in_([ln.id for ln in lines]))
                .group_by(SaleReturnLine.bill_line_id)
            )
        ).all()
    )
    payments = await ctx.db.scalars(
        select(Payment)
        .where(Payment.reference_type == "bill", Payment.reference_id == str(bill.id))
        .order_by(Payment.id)
    )
    out = BillOut.model_validate(bill)
    out.credit_paise = bill.total_paise - bill.paid_paise
    out.lines = []
    for ln in lines:
        item = BillLineOut.model_validate(ln)
        item.returned_base = int(returned.get(ln.id, 0))
        item.total_paise = ln.taxable_paise + ln.cgst_paise + ln.sgst_paise + ln.igst_paise
        out.lines.append(item)
    out.payments = [BillPaymentOut.model_validate(p) for p in payments]
    return out


async def get_bill(ctx: Ctx, bill_id: uuid.UUID) -> BillOut:
    _view(ctx)
    return await _bill_out(ctx, await _bill(ctx, bill_id))


async def list_bills(
    ctx: Ctx,
    *,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    party_id: uuid.UUID | None,
    status: str | None,
    before_id: uuid.UUID | None,
    limit: int,
) -> list[BillSummaryOut]:
    _view(ctx)
    stmt = select(Bill).order_by(Bill.id.desc()).limit(limit)
    if ctx.tenant.location_ids is not None:
        stmt = stmt.where(Bill.location_id.in_(ctx.tenant.location_ids))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Bill.bill_number.ilike(like), Bill.party_name.ilike(like), Bill.party_phone.ilike(like)))
    if date_from is not None:
        stmt = stmt.where(Bill.bill_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Bill.bill_date <= date_to)
    if party_id is not None:
        stmt = stmt.where(Bill.party_id == party_id)
    if status:
        stmt = stmt.where(Bill.status == status)
    if before_id is not None:
        stmt = stmt.where(Bill.id < before_id)
    return [BillSummaryOut.model_validate(b) for b in await ctx.db.scalars(stmt)]


# --- selling ---------------------------------------------------------------------------------------------


async def create_sale(ctx: Ctx, data: SaleIn) -> BillOut:
    require_module(ctx, ModuleKey.SELL)
    require_permission(ctx, Perm.BILLS_CREATE)
    await inventory.require_location(ctx, data.location_id)

    business = await platform.get_business(ctx.db, ctx.tenant.business_id)
    party = await parties.party_for_document(ctx, "customer", data.party_id) if data.party_id else None
    items = [
        await catalog.resolve_sale_item(ctx, ln.product_id, ln.variety_id, ln.grade_id, ln.unit_id) for ln in data.lines
    ]

    # GST: same state -> CGST + SGST, different state -> IGST. A business without a GSTIN cannot charge GST.
    seller_state = _gst_state(business.gstin)
    buyer_state = _gst_state(party.gstin if party else None) or data.place_of_supply or seller_state
    inter_state = bool(seller_state and buyer_state and seller_state != buyer_state)
    taxed = any(item.gst_rate_bp > 0 for item in items)
    if taxed and not business.gstin:
        raise Unprocessable("This business has no GSTIN, so it cannot charge GST", code="gst_needs_gstin")
    doc_type = "tax_invoice" if taxed else "bill_of_supply"

    results: list[LineResult] = [
        price_line(
            LineInput(ln.quantity, item.unit_base_factor, ln.unit_price_paise, item.gst_rate_bp),
            inter_state=inter_state,
        )
        for ln, item in zip(data.lines, items, strict=True)
    ]
    totals = bill_totals(results)
    if totals.total_paise <= 0:
        raise Unprocessable("A bill needs a total above zero", code="zero_total")

    paid = sum(p.amount_paise for p in data.payments)
    if paid > totals.total_paise:
        raise Unprocessable("Payments are more than the bill total", code="overpaid")
    credit = totals.total_paise - paid
    if credit > 0:
        if party is None:
            raise Unprocessable("Choose a customer to sell on credit", code="credit_needs_customer")
        if party.credit_limit_paise is not None and party.balance_paise + credit > party.credit_limit_paise:
            raise Unprocessable("This would go over the customer's credit limit", code="credit_limit_exceeded")

    day = today_ist()
    number, fy, seq = await next_number(ctx, SALE_SERIES, day)
    bill = Bill(
        id=uuid7(),
        series=SALE_SERIES,
        fy=fy,
        seq=seq,
        bill_number=number,
        doc_type=doc_type,
        bill_date=day,
        location_id=data.location_id,
        party_id=party.id if party else None,
        party_name=party.name if party else None,
        party_phone=party.phone if party else None,
        party_gstin=party.gstin if party else None,
        party_address=party.address if party else None,
        seller_name=business.name,
        seller_gstin=business.gstin,
        seller_address=business.address,
        seller_phone=business.phone,
        place_of_supply=buyer_state if business.gstin else None,
        supply_type="inter" if inter_state else "intra",
        taxable_paise=totals.taxable_paise,
        cgst_paise=totals.cgst_paise,
        sgst_paise=totals.sgst_paise,
        igst_paise=totals.igst_paise,
        round_off_paise=totals.round_off_paise,
        total_paise=totals.total_paise,
        paid_paise=paid,
        status="active",
        note=data.note,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(bill)
    await ctx.db.flush()
    for i, (ln, item, res) in enumerate(zip(data.lines, items, results, strict=True), start=1):
        ctx.db.add(
            BillLine(
                bill_id=bill.id,
                line_no=i,
                product_id=item.stock.product_id,
                variety_id=item.stock.variety_id,
                grade_id=item.stock.grade_id,
                unit_id=item.unit_id,
                description=item.description,
                description_ta=item.description_ta,
                hsn_code=item.hsn_code,
                unit_code=item.unit_code,
                unit_base_factor=item.unit_base_factor,
                quantity_base=ln.quantity,
                unit_price_paise=ln.unit_price_paise,
                gst_rate_bp=item.gst_rate_bp,
                taxable_paise=res.taxable_paise,
                cgst_paise=res.cgst_paise,
                sgst_paise=res.sgst_paise,
                igst_paise=res.igst_paise,
            )
        )
    await ctx.db.flush()

    # stock out, in a fixed order so two bills selling the same goods cannot deadlock each other
    for ln, item in sorted(zip(data.lines, items, strict=True), key=lambda pair: str(pair[1].stock.product_id)):
        await inventory.post_document_movement(
            ctx,
            data.location_id,
            item.stock,
            -ln.quantity,
            "sale",
            reference_type="bill",
            reference_id=str(bill.id),
            reason=number,
        )

    if party:
        await ledger.post_party_entry(
            ctx, party.id, "sale", totals.total_paise, note=number, reference_type="bill", reference_id=str(bill.id)
        )
    for pay in data.payments:
        await ledger.record_payment(
            ctx,
            party_id=party.id if party else None,
            direction="in",
            method=pay.method,
            amount_paise=pay.amount_paise,
            reference_type="bill",
            reference_id=str(bill.id),
            note=number,
        )

    await ctx.db.refresh(bill)
    out = await _bill_out(ctx, bill)
    await audit.record(ctx, "bill.create", entity_type="bill", entity_id=bill.id, after=out)
    return out


# --- cancelling ------------------------------------------------------------------------------------------


async def void_bill(ctx: Ctx, bill_id: uuid.UUID, data: VoidIn) -> BillOut:
    """Cancel a bill: it stays on record, marked void with a reason; stock, ledger and payments are reversed."""
    require_module(ctx, ModuleKey.BILLS)
    require_permission(ctx, Perm.BILLS_VOID)
    bill = await _bill(ctx, bill_id)
    if bill.status == "void":
        raise Conflict("This bill is already cancelled", code="already_void")
    has_returns = await ctx.db.scalar(select(SaleReturn.id).where(SaleReturn.bill_id == bill.id).limit(1))
    if has_returns is not None:
        raise Conflict("Goods were already returned against this bill", code="has_returns")
    before = await _bill_out(ctx, bill)

    ref = str(bill.id)
    await inventory.reverse_document_movements(ctx, "bill", ref, data.reason)
    await ledger.reverse_document(ctx, "bill", ref, data.reason)
    bill.status = "void"
    bill.void_reason = data.reason
    bill.voided_at = datetime.now(UTC)
    bill.voided_by = ctx.actor.user_id
    await ctx.db.flush()
    await ctx.db.refresh(bill)
    out = await _bill_out(ctx, bill)
    await audit.record(ctx, "bill.void", entity_type="bill", entity_id=bill.id, before=before, after=out)
    return out


# --- returns (credit notes) ------------------------------------------------------------------------------


async def _return_out(ctx: Ctx, ret: SaleReturn, bill_number: str) -> ReturnOut:
    rows = (
        await ctx.db.execute(
            select(SaleReturnLine, BillLine.description)
            .join(BillLine, BillLine.id == SaleReturnLine.bill_line_id)
            .where(SaleReturnLine.return_id == ret.id)
            .order_by(BillLine.line_no)
        )
    ).all()
    return ReturnOut(
        id=ret.id,
        return_number=ret.return_number,
        bill_id=ret.bill_id,
        bill_number=bill_number,
        return_date=ret.return_date,
        location_id=ret.location_id,
        taxable_paise=ret.taxable_paise,
        cgst_paise=ret.cgst_paise,
        sgst_paise=ret.sgst_paise,
        igst_paise=ret.igst_paise,
        round_off_paise=ret.round_off_paise,
        total_paise=ret.total_paise,
        refund_paise=ret.refund_paise,
        refund_method=ret.refund_method,
        reason=ret.reason,
        created_at=ret.created_at,
        lines=[
            ReturnLineOut(
                bill_line_id=line.bill_line_id,
                description=description,
                quantity_base=line.quantity_base,
                taxable_paise=line.taxable_paise,
                cgst_paise=line.cgst_paise,
                sgst_paise=line.sgst_paise,
                igst_paise=line.igst_paise,
            )
            for line, description in rows
        ],
    )


async def list_returns(ctx: Ctx, bill_id: uuid.UUID) -> list[ReturnOut]:
    _view(ctx)
    bill = await _bill(ctx, bill_id)
    rows = await ctx.db.scalars(select(SaleReturn).where(SaleReturn.bill_id == bill.id).order_by(SaleReturn.id))
    return [await _return_out(ctx, r, bill.bill_number) for r in rows]


async def create_return(ctx: Ctx, bill_id: uuid.UUID, data: ReturnIn) -> ReturnOut:
    require_module(ctx, ModuleKey.BILLS)
    require_permission(ctx, Perm.BILLS_RETURN)
    bill = await _bill(ctx, bill_id)
    if bill.status != "active":
        raise Unprocessable("A cancelled bill cannot take returns", code="bill_void")
    ids = [ln.bill_line_id for ln in data.lines]
    if len(set(ids)) != len(ids):
        raise Unprocessable("List each bill line once", code="duplicate_line")

    lines = {
        ln.id: ln
        for ln in await ctx.db.scalars(select(BillLine).where(BillLine.bill_id == bill.id, BillLine.id.in_(ids)))
    }
    if len(lines) != len(ids):
        raise NotFound("Bill line not found")
    already = dict(
        (
            await ctx.db.execute(
                select(SaleReturnLine.bill_line_id, func.sum(SaleReturnLine.quantity_base))
                .where(SaleReturnLine.bill_line_id.in_(ids))
                .group_by(SaleReturnLine.bill_line_id)
            )
        ).all()
    )
    inter = bill.supply_type == "inter"
    results: list[LineResult] = []
    for ln in data.lines:
        src = lines[ln.bill_line_id]
        if ln.quantity > src.quantity_base - int(already.get(src.id, 0)):
            raise Unprocessable("More than was sold is being returned", code="return_exceeds_sold")
        results.append(
            price_line(
                LineInput(ln.quantity, src.unit_base_factor, src.unit_price_paise, src.gst_rate_bp), inter_state=inter
            )
        )
    totals = bill_totals(results)
    if totals.total_paise <= 0:
        raise Unprocessable("The returned goods are worth nothing", code="zero_total")

    if data.refund_paise > totals.total_paise:
        raise Unprocessable("Refund is more than the credit note", code="overpaid")
    if data.refund_paise > 0 and data.refund_method is None:
        raise Unprocessable("Choose how the refund is paid", code="refund_method_required")
    if bill.party_id is None and data.refund_paise != totals.total_paise:
        raise Unprocessable("A walk-in customer must be refunded in full", code="walk_in_needs_full_refund")
    restock_at = data.location_id or bill.location_id

    day = today_ist()
    number, fy, seq = await next_number(ctx, RETURN_SERIES, day)
    ret = SaleReturn(
        id=uuid7(),
        bill_id=bill.id,
        series=RETURN_SERIES,
        fy=fy,
        seq=seq,
        return_number=number,
        return_date=day,
        location_id=restock_at if data.restock else None,
        taxable_paise=totals.taxable_paise,
        cgst_paise=totals.cgst_paise,
        sgst_paise=totals.sgst_paise,
        igst_paise=totals.igst_paise,
        round_off_paise=totals.round_off_paise,
        total_paise=totals.total_paise,
        refund_paise=data.refund_paise,
        refund_method=data.refund_method if data.refund_paise > 0 else None,
        reason=data.reason,
        created_by=ctx.actor.user_id,
    )
    ctx.db.add(ret)
    await ctx.db.flush()
    for ln, res in zip(data.lines, results, strict=True):
        ctx.db.add(
            SaleReturnLine(
                return_id=ret.id,
                bill_line_id=ln.bill_line_id,
                quantity_base=ln.quantity,
                taxable_paise=res.taxable_paise,
                cgst_paise=res.cgst_paise,
                sgst_paise=res.sgst_paise,
                igst_paise=res.igst_paise,
            )
        )
    await ctx.db.flush()

    if data.restock:
        for ln in data.lines:
            src = lines[ln.bill_line_id]
            item = catalog.StockItem(src.product_id, src.variety_id, src.grade_id, kind="")
            await inventory.post_document_movement(
                ctx,
                restock_at,
                item,
                ln.quantity,
                "sale_return",
                reference_type="sale_return",
                reference_id=str(ret.id),
                reason=number,
            )
    if bill.party_id is not None:
        await ledger.post_party_entry(
            ctx,
            bill.party_id,
            "sale_return",
            -totals.total_paise,
            note=f"{number} ({bill.bill_number})",
            reference_type="sale_return",
            reference_id=str(ret.id),
        )
    if data.refund_paise > 0 and data.refund_method is not None:
        await ledger.record_payment(
            ctx,
            party_id=bill.party_id,
            direction="out",
            method=data.refund_method,
            amount_paise=data.refund_paise,
            reference_type="sale_return",
            reference_id=str(ret.id),
            note=number,
        )

    await ctx.db.refresh(ret)
    out = await _return_out(ctx, ret, bill.bill_number)
    await audit.record(ctx, "bill.return", entity_type="sale_return", entity_id=ret.id, after=out)
    return out


# --- numbers for reports ---------------------------------------------------------------------------------


async def sales_totals(ctx: Ctx, date_from: date, date_to: date) -> dict[str, int]:
    """Active-bill totals for a date range (inclusive), less returns dated in the same range."""
    _view(ctx)
    bills = (
        await ctx.db.execute(
            select(
                func.count(Bill.id),
                func.coalesce(func.sum(Bill.taxable_paise), 0),
                func.coalesce(func.sum(Bill.cgst_paise + Bill.sgst_paise + Bill.igst_paise), 0),
                func.coalesce(func.sum(Bill.total_paise), 0),
                func.coalesce(func.sum(Bill.paid_paise), 0),
            ).where(Bill.status == "active", Bill.bill_date >= date_from, Bill.bill_date <= date_to)
        )
    ).one()
    returns = (
        await ctx.db.execute(
            select(func.count(SaleReturn.id), func.coalesce(func.sum(SaleReturn.total_paise), 0)).where(
                SaleReturn.return_date >= date_from, SaleReturn.return_date <= date_to
            )
        )
    ).one()
    return {
        "bills": int(bills[0]),
        "taxable_paise": int(bills[1]),
        "tax_paise": int(bills[2]),
        "total_paise": int(bills[3]),
        "collected_paise": int(bills[4]),
        "returns": int(returns[0]),
        "returns_paise": int(returns[1]),
    }


async def sales_by_day(ctx: Ctx, date_from: date, date_to: date) -> list[dict[str, int | str]]:
    _view(ctx)
    rows = await ctx.db.execute(
        select(Bill.bill_date, func.count(Bill.id), func.sum(Bill.total_paise))
        .where(Bill.status == "active", Bill.bill_date >= date_from, Bill.bill_date <= date_to)
        .group_by(Bill.bill_date)
        .order_by(Bill.bill_date)
    )
    return [{"date": d.isoformat(), "bills": int(n), "total_paise": int(total)} for d, n, total in rows]


async def sales_by_product(ctx: Ctx, date_from: date, date_to: date) -> list[dict[str, int | str]]:
    """What sold, from active bills only (returns are reported separately). Quantity is in base units."""
    _view(ctx)
    total = func.sum(BillLine.taxable_paise + BillLine.cgst_paise + BillLine.sgst_paise + BillLine.igst_paise)
    rows = await ctx.db.execute(
        select(
            BillLine.product_id,
            func.min(BillLine.description),
            func.sum(BillLine.quantity_base),
            func.sum(BillLine.taxable_paise),
            total,
        )
        .join(Bill, Bill.id == BillLine.bill_id)
        .where(Bill.status == "active", Bill.bill_date >= date_from, Bill.bill_date <= date_to)
        .group_by(BillLine.product_id)
        .order_by(total.desc())
    )
    return [
        {
            "product_id": str(pid),
            "description": desc,
            "quantity_base": int(qty),
            "taxable_paise": int(taxable),
            "total_paise": int(tot),
        }
        for pid, desc, qty, taxable, tot in rows
    ]


async def gst_summary(ctx: Ctx, date_from: date, date_to: date) -> list[dict[str, int]]:
    """Tax by GST rate for the range: sales on active bills less returns (credit notes) dated in the range."""
    _view(ctx)
    sold = await ctx.db.execute(
        select(
            BillLine.gst_rate_bp,
            func.sum(BillLine.taxable_paise),
            func.sum(BillLine.cgst_paise),
            func.sum(BillLine.sgst_paise),
            func.sum(BillLine.igst_paise),
        )
        .join(Bill, Bill.id == BillLine.bill_id)
        .where(Bill.status == "active", Bill.bill_date >= date_from, Bill.bill_date <= date_to)
        .group_by(BillLine.gst_rate_bp)
    )
    taken_back = await ctx.db.execute(
        select(
            BillLine.gst_rate_bp,
            func.sum(SaleReturnLine.taxable_paise),
            func.sum(SaleReturnLine.cgst_paise),
            func.sum(SaleReturnLine.sgst_paise),
            func.sum(SaleReturnLine.igst_paise),
        )
        .join(BillLine, BillLine.id == SaleReturnLine.bill_line_id)
        .join(SaleReturn, SaleReturn.id == SaleReturnLine.return_id)
        .where(SaleReturn.return_date >= date_from, SaleReturn.return_date <= date_to)
        .group_by(BillLine.gst_rate_bp)
    )
    rates: dict[int, list[int]] = {}
    for rate, taxable, cgst, sgst, igst in sold:
        rates.setdefault(int(rate), [0] * 4)
        for i, v in enumerate((taxable, cgst, sgst, igst)):
            rates[int(rate)][i] += int(v)
    for rate, taxable, cgst, sgst, igst in taken_back:
        rates.setdefault(int(rate), [0] * 4)
        for i, v in enumerate((taxable, cgst, sgst, igst)):
            rates[int(rate)][i] -= int(v)
    return [
        {"gst_rate_bp": rate, "taxable_paise": v[0], "cgst_paise": v[1], "sgst_paise": v[2], "igst_paise": v[3]}
        for rate, v in sorted(rates.items())
    ]
