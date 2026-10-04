"""Append-only party (money) and crate ledgers. Never UPDATE or DELETE: fix mistakes with a reversing entry."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TenantMixin

PARTY_ENTRY_TYPES = (
    "opening",
    "sale",
    "sale_return",
    "purchase",
    "purchase_return",
    "payment_in",
    "payment_out",
    "adjustment",
    "reversal",
)
CRATE_ENTRY_TYPES = ("issued", "returned", "adjustment", "reversal")
PAYMENT_METHODS = ("cash", "upi", "card", "bank", "cheque", "other")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class PartyLedgerEntry(IdMixin, TenantMixin, Base):
    """``amount_paise`` > 0: the party owes the business more; < 0: the business owes the party more."""

    __tablename__ = "party_ledger_entries"
    __table_args__ = (
        # composite FK: the DB itself guarantees the party belongs to the same business as the entry
        ForeignKeyConstraint(["business_id", "party_id"], ["parties.business_id", "parties.id"]),
        CheckConstraint(f"entry_type IN ({_in(PARTY_ENTRY_TYPES)})", name="entry_type"),
        CheckConstraint("amount_paise <> 0", name="amount_nonzero"),
        Index("ix_party_ledger_entries_party", "business_id", "party_id", "id"),
    )

    party_id: Mapped[uuid.UUID]
    entry_type: Mapped[str] = mapped_column(String(20))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[str | None] = mapped_column(String(64))
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("party_ledger_entries.id", ondelete="RESTRICT"), unique=True
    )
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CrateLedgerEntry(IdMixin, TenantMixin, Base):
    """``quantity`` > 0: crates issued to the party (they hold more); < 0: crates returned."""

    __tablename__ = "crate_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "party_id"], ["parties.business_id", "parties.id"]),
        CheckConstraint(f"entry_type IN ({_in(CRATE_ENTRY_TYPES)})", name="entry_type"),
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        Index("ix_crate_ledger_entries_party", "business_id", "party_id", "id"),
    )

    party_id: Mapped[uuid.UUID]
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    entry_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(BigInteger)
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[str | None] = mapped_column(String(64))
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crate_ledger_entries.id", ondelete="RESTRICT"), unique=True
    )
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Payment(IdMixin, TenantMixin, Base):
    """Money that actually moved (cash, UPI, ...). Append-only; a mistake is undone by a reversing payment.

    ``direction`` 'in' is money received (from a customer), 'out' is money paid (to a supplier, or a refund).
    """

    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "party_id"], ["parties.business_id", "parties.id"]),
        CheckConstraint("direction IN ('in', 'out')", name="direction"),
        CheckConstraint(f"method IN ({_in(PAYMENT_METHODS)})", name="method"),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        Index("ix_payments_party", "business_id", "party_id", "id"),
        Index("ix_payments_reference", "business_id", "reference_type", "reference_id"),
    )

    party_id: Mapped[uuid.UUID | None]
    direction: Mapped[str] = mapped_column(String(3))
    method: Mapped[str] = mapped_column(String(10))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    reference_type: Mapped[str | None] = mapped_column(String(30))  # 'bill', 'purchase', 'sale_return' or none
    reference_id: Mapped[str | None] = mapped_column(String(64))
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), unique=True)
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
