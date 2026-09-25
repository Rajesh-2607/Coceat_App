from sqlalchemy import CheckConstraint, String, UniqueConstraint
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
