"""Purchase entries: stock received from a supplier, with what was paid and what is owed."""

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


class Purchase(IdMixin, TenantMixin, Base):
    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        UniqueConstraint("business_id", "purchase_number"),
        UniqueConstraint("business_id", "fy", "series", "seq"),
        ForeignKeyConstraint(["business_id", "supplier_id"], ["parties.business_id", "parties.id"]),
        CheckConstraint("status IN ('active', 'void')", name="status"),
        CheckConstraint("total_paise >= 0 AND paid_paise >= 0 AND paid_paise <= total_paise", name="amounts"),
        CheckConstraint(
            "status = 'active' OR (void_reason IS NOT NULL AND voided_at IS NOT NULL)", name="void_details"
        ),
        Index("ix_purchases_date", "business_id", "purchase_date", "id"),
    )

    series: Mapped[str] = mapped_column(String(3))
    fy: Mapped[str] = mapped_column(String(5))
    seq: Mapped[int] = mapped_column(BigInteger)
    purchase_number: Mapped[str] = mapped_column(String(16))
    purchase_date: Mapped[date] = mapped_column(Date)
    supplier_id: Mapped[uuid.UUID]
    supplier_name: Mapped[str] = mapped_column(String(120))  # as it was when the goods came in
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    supplier_bill_no: Mapped[str | None] = mapped_column(String(40))
    total_paise: Mapped[int] = mapped_column(BigInteger)
    paid_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(10), default="active")
    void_reason: Mapped[str | None] = mapped_column(String(300))
    voided_at: Mapped[datetime | None]
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PurchaseLine(IdMixin, TenantMixin, Base):
    __tablename__ = "purchase_lines"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "purchase_id"], ["purchases.business_id", "purchases.id"]),
        UniqueConstraint("purchase_id", "line_no"),
        CheckConstraint("quantity_base > 0 AND unit_cost_paise >= 0 AND amount_paise >= 0", name="amounts"),
    )

    purchase_id: Mapped[uuid.UUID]
    line_no: Mapped[int] = mapped_column(SmallInteger)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variety_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("varieties.id", ondelete="RESTRICT"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(300))
    description_ta: Mapped[str | None] = mapped_column(String(400))
    unit_code: Mapped[str] = mapped_column(String(20))
    unit_base_factor: Mapped[int] = mapped_column(BigInteger)
    quantity_base: Mapped[int] = mapped_column(BigInteger)
    unit_cost_paise: Mapped[int] = mapped_column(BigInteger)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
