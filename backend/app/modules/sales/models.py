"""Bills and sale returns. A bill is a legal document: its rows are immutable, and a cancelled bill is only marked
void (with who, when and why); the number stays used so the sequence has no gaps."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TenantMixin

DOC_TYPES = ("tax_invoice", "bill_of_supply")


class Bill(IdMixin, TenantMixin, Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),  # target of the lines' composite foreign key
        UniqueConstraint("business_id", "bill_number"),
        UniqueConstraint("business_id", "fy", "series", "seq"),
        ForeignKeyConstraint(["business_id", "party_id"], ["parties.business_id", "parties.id"]),
        CheckConstraint("doc_type IN ('tax_invoice', 'bill_of_supply')", name="doc_type"),
        CheckConstraint("status IN ('active', 'void')", name="status"),
        CheckConstraint("supply_type IN ('intra', 'inter')", name="supply_type"),
        CheckConstraint("total_paise >= 0 AND paid_paise >= 0 AND paid_paise <= total_paise", name="amounts"),
        CheckConstraint("mod(total_paise, 100) = 0", name="whole_rupees"),
        CheckConstraint("doc_type <> 'tax_invoice' OR seller_gstin IS NOT NULL", name="tax_invoice_needs_gstin"),
        CheckConstraint(
            "status = 'active' OR (void_reason IS NOT NULL AND voided_at IS NOT NULL)", name="void_details"
        ),
        Index("ix_bills_date", "business_id", "bill_date", "id"),
        Index("ix_bills_party", "business_id", "party_id", "id"),
    )

    series: Mapped[str] = mapped_column(String(3))
    fy: Mapped[str] = mapped_column(String(5))
    seq: Mapped[int] = mapped_column(BigInteger)
    bill_number: Mapped[str] = mapped_column(String(16))
    doc_type: Mapped[str] = mapped_column(String(20))
    bill_date: Mapped[date] = mapped_column(Date)  # Indian calendar day
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    party_id: Mapped[uuid.UUID | None]
    # who it was sold to and by, as printed on the bill (later edits to the party never change an old bill)
    party_name: Mapped[str | None] = mapped_column(String(120))
    party_phone: Mapped[str | None] = mapped_column(String(16))
    party_gstin: Mapped[str | None] = mapped_column(String(15))
    party_address: Mapped[str | None] = mapped_column(String(300))
    seller_name: Mapped[str] = mapped_column(String(120))
    seller_gstin: Mapped[str | None] = mapped_column(String(15))
    seller_address: Mapped[str | None] = mapped_column(String(300))
    seller_phone: Mapped[str | None] = mapped_column(String(16))
    place_of_supply: Mapped[str | None] = mapped_column(String(2))  # GST state code
    supply_type: Mapped[str] = mapped_column(String(5))
    taxable_paise: Mapped[int] = mapped_column(BigInteger)
    cgst_paise: Mapped[int] = mapped_column(BigInteger)
    sgst_paise: Mapped[int] = mapped_column(BigInteger)
    igst_paise: Mapped[int] = mapped_column(BigInteger)
    round_off_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    paid_paise: Mapped[int] = mapped_column(BigInteger)  # collected when the bill was made; the rest is on credit
    status: Mapped[str] = mapped_column(String(10), default="active")
    void_reason: Mapped[str | None] = mapped_column(String(300))
    voided_at: Mapped[datetime | None]
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BillLine(IdMixin, TenantMixin, Base):
    __tablename__ = "bill_lines"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        ForeignKeyConstraint(["business_id", "bill_id"], ["bills.business_id", "bills.id"]),
        UniqueConstraint("bill_id", "line_no"),
        CheckConstraint("quantity_base > 0 AND unit_price_paise >= 0", name="amounts"),
    )

    bill_id: Mapped[uuid.UUID]
    line_no: Mapped[int] = mapped_column(SmallInteger)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variety_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("varieties.id", ondelete="RESTRICT"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(300))  # "Banana · Robusta · A" as printed
    description_ta: Mapped[str | None] = mapped_column(String(400))
    hsn_code: Mapped[str | None] = mapped_column(String(8))
    unit_code: Mapped[str] = mapped_column(String(20))
    unit_base_factor: Mapped[int] = mapped_column(BigInteger)
    quantity_base: Mapped[int] = mapped_column(BigInteger)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)  # per unit, before GST
    gst_rate_bp: Mapped[int] = mapped_column(SmallInteger)
    taxable_paise: Mapped[int] = mapped_column(BigInteger)
    cgst_paise: Mapped[int] = mapped_column(BigInteger)
    sgst_paise: Mapped[int] = mapped_column(BigInteger)
    igst_paise: Mapped[int] = mapped_column(BigInteger)


class SaleReturn(IdMixin, TenantMixin, Base):
    """A credit note against one bill. Append-only."""

    __tablename__ = "sale_returns"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        UniqueConstraint("business_id", "return_number"),
        UniqueConstraint("business_id", "fy", "series", "seq"),
        ForeignKeyConstraint(["business_id", "bill_id"], ["bills.business_id", "bills.id"]),
        CheckConstraint("total_paise >= 0 AND refund_paise >= 0 AND refund_paise <= total_paise", name="amounts"),
        Index("ix_sale_returns_bill", "business_id", "bill_id"),
    )

    bill_id: Mapped[uuid.UUID]
    series: Mapped[str] = mapped_column(String(3))
    fy: Mapped[str] = mapped_column(String(5))
    seq: Mapped[int] = mapped_column(BigInteger)
    return_number: Mapped[str] = mapped_column(String(16))
    return_date: Mapped[date] = mapped_column(Date)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    taxable_paise: Mapped[int] = mapped_column(BigInteger)
    cgst_paise: Mapped[int] = mapped_column(BigInteger)
    sgst_paise: Mapped[int] = mapped_column(BigInteger)
    igst_paise: Mapped[int] = mapped_column(BigInteger)
    round_off_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    refund_paise: Mapped[int] = mapped_column(BigInteger)  # paid back now; the rest reduces what the party owes
    refund_method: Mapped[str | None] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SaleReturnLine(IdMixin, TenantMixin, Base):
    __tablename__ = "sale_return_lines"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "return_id"], ["sale_returns.business_id", "sale_returns.id"]),
        ForeignKeyConstraint(["business_id", "bill_line_id"], ["bill_lines.business_id", "bill_lines.id"]),
        CheckConstraint("quantity_base > 0", name="quantity_positive"),
        Index("ix_sale_return_lines_bill_line", "business_id", "bill_line_id"),
    )

    return_id: Mapped[uuid.UUID]
    bill_line_id: Mapped[uuid.UUID]
    quantity_base: Mapped[int] = mapped_column(BigInteger)
    taxable_paise: Mapped[int] = mapped_column(BigInteger)
    cgst_paise: Mapped[int] = mapped_column(BigInteger)
    sgst_paise: Mapped[int] = mapped_column(BigInteger)
    igst_paise: Mapped[int] = mapped_column(BigInteger)
