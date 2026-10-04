"""Read-only summaries assembled from other modules' services (each does its own permission checks)."""

from collections.abc import Awaitable
from datetime import date, datetime, time, timedelta

from app.core.context import Ctx
from app.core.errors import Forbidden, Unprocessable
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.catalog import service as catalog
from app.modules.inventory import service as inventory
from app.modules.ledger import service as ledger
from app.modules.parties import service as parties
from app.modules.platform.modules import ModuleKey
from app.modules.purchases import service as purchases
from app.modules.reports.schemas import (
    DayBookOut,
    GstReportOut,
    GstRow,
    HomeOut,
    OutstandingOut,
    PurchaseTotals,
    SalesDayRow,
    SalesProductRow,
    SalesReportOut,
    SalesTotals,
    WastageReportOut,
    WastageRow,
)
from app.modules.sales import service as sales
from app.modules.sales.service import IST, today_ist


async def _allowed[T](call: Awaitable[T]) -> T | None:
    try:
        return await call
    except Forbidden:
        return None


async def home(ctx: Ctx) -> HomeOut:
    today = today_ist()
    today_sales = await _allowed(sales.sales_totals(ctx, today, today))
    locations = await _allowed(inventory.list_locations(ctx))
    products = await _allowed(catalog.list_products(ctx))
    customers = await _allowed(parties.summary(ctx, "customer"))
    suppliers = await _allowed(parties.summary(ctx, "supplier"))
    stock = await _allowed(inventory.stock_counts(ctx))
    crates = await _allowed(ledger.crate_balances(ctx))
    return HomeOut(
        today_bills=today_sales["bills"] if today_sales is not None else None,
        today_sales_paise=today_sales["total_paise"] if today_sales is not None else None,
        locations=len(locations) if locations is not None else None,
        products=len(products) if products is not None else None,
        customers=customers.count if customers else None,
        suppliers=suppliers.count if suppliers else None,
        stock_items=stock[0] if stock else None,
        negative_stock_items=stock[1] if stock else None,
        receivable_paise=customers.owed_to_us_paise if customers else None,
        payable_paise=suppliers.we_owe_paise if suppliers else None,
        crates_outstanding=sum(c.crates_held for c in crates if c.crates_held > 0) if crates is not None else None,
        top_owing_customers=customers.top_owing if customers else [],
    )


# --- reports (need the Reports module and permission, plus whatever the underlying data needs) ---------------


def _reports(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.REPORTS)
    require_permission(ctx, Perm.REPORTS_VIEW)


def _range(date_from: date, date_to: date) -> None:
    if date_to < date_from or (date_to - date_from).days > 366:
        raise Unprocessable("Choose a date range of at most a year", code="bad_range")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=IST)
    return start, start + timedelta(days=1)


async def day_book(ctx: Ctx, day: date) -> DayBookOut:
    _reports(ctx)
    start, end = _day_bounds(day)
    sales_totals = await _allowed(sales.sales_totals(ctx, day, day))
    purchase_totals = await _allowed(purchases.purchase_totals(ctx, day, day))
    payments = await _allowed(ledger.payment_totals(ctx, start, end))
    return DayBookOut(
        date=day,
        sales=SalesTotals(**sales_totals) if sales_totals is not None else None,
        purchases=PurchaseTotals(**purchase_totals) if purchase_totals is not None else None,
        payments=payments,
    )


async def sales_report(ctx: Ctx, date_from: date, date_to: date) -> SalesReportOut:
    _reports(ctx)
    _range(date_from, date_to)
    return SalesReportOut(
        date_from=date_from,
        date_to=date_to,
        totals=SalesTotals(**await sales.sales_totals(ctx, date_from, date_to)),
        by_day=[SalesDayRow(**r) for r in await sales.sales_by_day(ctx, date_from, date_to)],
        by_product=[SalesProductRow(**r) for r in await sales.sales_by_product(ctx, date_from, date_to)],
    )


async def gst_report(ctx: Ctx, date_from: date, date_to: date) -> GstReportOut:
    _reports(ctx)
    _range(date_from, date_to)
    rows = [GstRow(**r) for r in await sales.gst_summary(ctx, date_from, date_to)]
    return GstReportOut(
        date_from=date_from,
        date_to=date_to,
        rows=rows,
        total_tax_paise=sum(r.cgst_paise + r.sgst_paise + r.igst_paise for r in rows),
    )


async def outstanding_report(ctx: Ctx) -> OutstandingOut:
    _reports(ctx)
    customers = await parties.outstanding(ctx, "customer")
    suppliers = await parties.outstanding(ctx, "supplier")
    return OutstandingOut(
        customers=customers,
        suppliers=suppliers,
        owed_to_us_paise=sum(c.balance_paise for c in customers if c.balance_paise > 0)
        + sum(s.balance_paise for s in suppliers if s.balance_paise > 0),
        we_owe_paise=-sum(p.balance_paise for p in customers + suppliers if p.balance_paise < 0),
    )


async def wastage_report(ctx: Ctx, date_from: date, date_to: date) -> WastageReportOut:
    _reports(ctx)
    _range(date_from, date_to)
    start, _ = _day_bounds(date_from)
    _, end = _day_bounds(date_to)
    rows = await inventory.wastage_summary(ctx, start, end)
    return WastageReportOut(date_from=date_from, date_to=date_to, rows=[WastageRow(**r) for r in rows])
