import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class Location(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("business_id", "name"),
        CheckConstraint("kind IN ('shop', 'godown', 'cold_storage', 'other')", name="kind"),
    )

    name: Mapped[str] = mapped_column(String(80))
    name_ta: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="shop")
    is_active: Mapped[bool] = mapped_column(default=True)


MOVEMENT_TYPES = (
    "opening",
    "adjustment",
    "transfer_out",
    "transfer_in",
    "wastage",
    "reversal",
    "purchase",
    "sale",
    "sale_return",
)
WASTAGE_REASONS = ("rotten", "damaged", "shrinkage", "spoiled_in_transit", "other")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class StockMovement(IdMixin, TenantMixin, Base):
    """Append-only stock ledger. ``quantity`` is signed, in the product's base unit (grams or pieces).

    Balance = SUM(quantity) per (location, product, variety, grade). Fix a mistake with a reversing entry.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(f"movement_type IN ({_in(MOVEMENT_TYPES)})", name="movement_type"),
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        Index("ix_stock_movements_item", "business_id", "location_id", "product_id"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variety_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("varieties.id", ondelete="RESTRICT"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(BigInteger)
    movement_type: Mapped[str] = mapped_column(String(20))
    reference_type: Mapped[str | None] = mapped_column(String(30))
    reference_id: Mapped[str | None] = mapped_column(String(64))
    reversal_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="RESTRICT"), unique=True
    )
    reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StockTransfer(IdMixin, TenantMixin, Base):
    """Append-only header. Its lines are the paired transfer_out / transfer_in movements (reference_id = id)."""

    __tablename__ = "stock_transfers"
    __table_args__ = (CheckConstraint("from_location_id <> to_location_id", name="different_locations"),)

    from_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    to_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WastageEntry(IdMixin, TenantMixin, Base):
    """Append-only. ``movement_id`` is the stock movement it wrote."""

    __tablename__ = "wastage_entries"
    __table_args__ = (
        CheckConstraint(f"reason_code IN ({_in(WASTAGE_REASONS)})", name="reason_code"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    variety_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("varieties.id", ondelete="RESTRICT"))
    grade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(BigInteger)
    reason_code: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(300))
    movement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_movements.id", ondelete="RESTRICT"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
