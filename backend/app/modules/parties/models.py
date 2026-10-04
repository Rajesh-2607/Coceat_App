from sqlalchemy import BigInteger, CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class Party(IdMixin, TenantMixin, TimestampMixin, Base):
    """A customer or a supplier. Money owed lives in the party ledger, never on this row."""

    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("business_id", "id"),  # target of the ledgers' composite foreign keys
        CheckConstraint("kind IN ('customer', 'supplier')", name="kind"),
        CheckConstraint("gstin IS NULL OR length(gstin) = 15", name="gstin_length"),
        CheckConstraint("credit_limit_paise IS NULL OR credit_limit_paise >= 0", name="credit_limit"),
        Index(
            "uq_parties_kind_phone",
            "business_id",
            "kind",
            "phone",
            unique=True,
            postgresql_where="phone IS NOT NULL",
        ),
    )

    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(120))
    name_ta: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(16))  # E.164
    address: Mapped[str | None] = mapped_column(String(300))
    gstin: Mapped[str | None] = mapped_column(String(15))
    credit_limit_paise: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True)
