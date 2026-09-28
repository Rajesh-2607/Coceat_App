"""Import every model so Base.metadata is complete (for Alembic and mapper configuration)."""

from app.core.idempotency import IdempotencyRecord
from app.core.numbering import BillSequence
from app.modules.accounts.models import Membership, OtpChallenge, User, UserSession
from app.modules.audit.models import AuditEvent
from app.modules.catalog.models import Grade, Product, Unit, Variety
from app.modules.inventory.models import Location, StockMovement, StockTransfer, WastageEntry
from app.modules.ledger.models import CrateLedgerEntry, PartyLedgerEntry, Payment
from app.modules.parties.models import Party
from app.modules.platform.models import Business, VerticalTemplate
from app.modules.purchases.models import Purchase, PurchaseLine
from app.modules.sales.models import Bill, BillLine, SaleReturn, SaleReturnLine

__all__ = [
    "AuditEvent",
    "Bill",
    "BillLine",
    "BillSequence",
    "Business",
    "CrateLedgerEntry",
    "Grade",
    "IdempotencyRecord",
    "Location",
    "Membership",
    "OtpChallenge",
    "Party",
    "PartyLedgerEntry",
    "Payment",
    "Product",
    "Purchase",
    "PurchaseLine",
    "SaleReturn",
    "SaleReturnLine",
    "StockMovement",
    "StockTransfer",
    "Unit",
    "User",
    "UserSession",
    "Variety",
    "VerticalTemplate",
    "WastageEntry",
]
