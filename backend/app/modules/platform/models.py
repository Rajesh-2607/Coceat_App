from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class VerticalTemplate(TimestampMixin, Base):
    """Configuration for a trade (banana, flower, ...). New verticals are rows here, not code."""

    __tablename__ = "vertical_templates"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_ta: Mapped[str] = mapped_column(String(120))
    default_modules: Mapped[list[str]] = mapped_column(default=list)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Business(IdMixin, TimestampMixin, Base):
    """Platform table (not tenant-scoped): the tenant itself."""

    __tablename__ = "businesses"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="status"),
        CheckConstraint("gstin IS NULL OR length(gstin) = 15", name="gstin_length"),
    )

    name: Mapped[str] = mapped_column(String(120))
    name_ta: Mapped[str | None] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    vertical_key: Mapped[str] = mapped_column(ForeignKey("vertical_templates.key"))
    enabled_modules: Mapped[list[str]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
