from datetime import date

from pydantic import BaseModel

from app.modules.ledger.schemas import MethodTotal
from app.modules.parties.schemas import PartyBalanceOut


class HomeOut(BaseModel):
    """Headline numbers for the Home page. A field is null when the member's role or the business's
    enabled modules don't allow that part (the API refuses those endpoints anyway)."""

    today_bills: int | None  # bills made today (cancelled ones excluded)
    today_sales_paise: int | None
    locations: int | None
    products: int | None
    customers: int | None
    suppliers: int | None
    stock_items: int | None  # distinct (location, product, variety, grade) rows with stock
    negative_stock_items: int | None
    receivable_paise: int | None  # customers owe the business
    payable_paise: int | None  # the business owes suppliers
    crates_outstanding: int | None  # crates currently held by parties
    top_owing_customers: list[PartyBalanceOut]


class SalesTotals(BaseModel):
    bills: int
    taxable_paise: int
    tax_paise: int
    total_paise: int
    collected_paise: int  # paid at the counter when the bills were made
    returns: int
    returns_paise: int


class PurchaseTotals(BaseModel):
    purchases: int
    total_paise: int
    paid_paise: int


class DayBookOut(BaseModel):
    """One day's money. A part is null when the business doesn't have that module (or the role can't see it)."""

    date: date
    sales: SalesTotals | None
    purchases: PurchaseTotals | None
    payments: list[MethodTotal] | None  # money in and out by method, including refunds and supplier payments


class SalesDayRow(BaseModel):
    date: date
    bills: int
    total_paise: int


class SalesProductRow(BaseModel):
    product_id: str
    description: str
    quantity_base: int  # grams or pieces
    taxable_paise: int
    total_paise: int


class SalesReportOut(BaseModel):
    date_from: date
    date_to: date
    totals: SalesTotals
    by_day: list[SalesDayRow]
    by_product: list[SalesProductRow]


class GstRow(BaseModel):
    gst_rate_bp: int
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int


class GstReportOut(BaseModel):
    date_from: date
    date_to: date
    rows: list[GstRow]
    total_tax_paise: int


class OutstandingOut(BaseModel):
    customers: list[PartyBalanceOut]  # they owe us
    suppliers: list[PartyBalanceOut]  # negative balance = we owe them
    owed_to_us_paise: int
    we_owe_paise: int


class WastageRow(BaseModel):
    reason_code: str
    product_id: str
    quantity_base: int


class WastageReportOut(BaseModel):
    date_from: date
    date_to: date
    rows: list[WastageRow]
