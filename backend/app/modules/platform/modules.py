"""Workspace module keys. Which are enabled per business is configuration (Business.enabled_modules)."""

from enum import StrEnum


class ModuleKey(StrEnum):
    SELL = "sell"
    STOCK = "stock"
    MONEY = "money"
    BUY = "buy"
    BILLS = "bills"
    CUSTOMERS = "customers"
    SUPPLIERS = "suppliers"
    WASTAGE = "wastage"
    REPORTS = "reports"
    STAFF = "staff"
    AUDIT = "audit"
    SETTINGS = "settings"


ALL_MODULES = frozenset(ModuleKey)
