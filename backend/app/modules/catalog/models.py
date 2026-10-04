import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class Unit(IdMixin, TenantMixin, TimestampMixin, Base):
    """A way to count or weigh. ``base_factor`` = grams (kind 'weight') or pieces (kind 'count') in one unit."""

    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("business_id", "code"),
        CheckConstraint("kind IN ('weight', 'count')", name="kind"),
        CheckConstraint("base_factor >= 1", name="base_factor"),
    )

    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(60))
    name_ta: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(10))
    base_factor: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(default=True)


class Grade(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "grades"
    __table_args__ = (UniqueConstraint("business_id", "name"),)

    name: Mapped[str] = mapped_column(String(40))
    name_ta: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(default=True)


class Product(IdMixin, TenantMixin, TimestampMixin, Base):
    """Stock of a product is held in its base unit: grams for 'weight' products, pieces for 'count'."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("business_id", "name"),
        CheckConstraint("kind IN ('weight', 'count')", name="kind"),
        CheckConstraint("default_price_paise IS NULL OR default_price_paise >= 0", name="price"),
        CheckConstraint("gst_rate_bp IN (0, 25, 300, 500, 1200, 1800, 2800)", name="gst_rate"),
    )

    name: Mapped[str] = mapped_column(String(120))
    name_ta: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"))  # default unit
    default_price_paise: Mapped[int | None] = mapped_column(BigInteger)  # per default unit
    gst_rate_bp: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0"
    )  # basis points: 500 = 5%; fresh produce is 0
    hsn_code: Mapped[str | None] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(default=True)


class Variety(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "varieties"
    __table_args__ = (UniqueConstraint("business_id", "product_id", "name"),)

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_ta: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True)
