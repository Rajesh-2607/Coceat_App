"""Roles and what they may do. Checked in the service layer (see accounts.service.require_permission)."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    BILLING = "billing"  # counter staff: sell, collect money
    STOCK = "stock"  # godown staff: receive, transfer, wastage
    VIEWER = "viewer"


class Perm(StrEnum):
    LOCATIONS_VIEW = "locations.view"
    LOCATIONS_MANAGE = "locations.manage"
    AUDIT_VIEW = "audit.view"
    STAFF_VIEW = "staff.view"
    STAFF_MANAGE = "staff.manage"
    CATALOG_VIEW = "catalog.view"
    CATALOG_MANAGE = "catalog.manage"
    PARTIES_VIEW = "parties.view"
    PARTIES_MANAGE = "parties.manage"
    STOCK_VIEW = "stock.view"
    STOCK_MOVE = "stock.move"  # receive opening stock, adjust, transfer, record wastage, reverse a movement
    CRATES_VIEW = "crates.view"
    CRATES_MANAGE = "crates.manage"
    BILLS_VIEW = "bills.view"
    BILLS_CREATE = "bills.create"  # make a sale bill
    BILLS_RETURN = "bills.return"  # take goods back against a bill
    BILLS_VOID = "bills.void"  # cancel a bill
    MONEY_VIEW = "money.view"
    MONEY_RECORD = "money.record"  # payments in and out
    PURCHASES_VIEW = "purchases.view"
    PURCHASES_CREATE = "purchases.create"
    PURCHASES_VOID = "purchases.void"
    REPORTS_VIEW = "reports.view"


_ALL = frozenset(Perm)
_VIEW = frozenset(
    {
        Perm.LOCATIONS_VIEW,
        Perm.CATALOG_VIEW,
        Perm.PARTIES_VIEW,
        Perm.STOCK_VIEW,
        Perm.CRATES_VIEW,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: _ALL,
    Role.MANAGER: _ALL - {Perm.STAFF_MANAGE},
    Role.BILLING: _VIEW
    | {
        Perm.PARTIES_MANAGE,
        Perm.CRATES_MANAGE,
        Perm.BILLS_VIEW,
        Perm.BILLS_CREATE,
        Perm.BILLS_RETURN,
        Perm.MONEY_VIEW,
        Perm.MONEY_RECORD,
    },
    Role.STOCK: _VIEW | {Perm.STOCK_MOVE, Perm.CRATES_MANAGE, Perm.PURCHASES_VIEW, Perm.PURCHASES_CREATE},
    Role.VIEWER: _VIEW | {Perm.BILLS_VIEW, Perm.MONEY_VIEW, Perm.PURCHASES_VIEW, Perm.REPORTS_VIEW},
}


def role_has(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return False
