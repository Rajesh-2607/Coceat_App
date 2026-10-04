"""Gap-free document numbers (bills, returns, purchases).

Numbers are sequential per business, financial year and series, at most 16 characters
(GST requires unique, consecutive invoice numbers of up to 16 characters). The counter row is locked with
``SELECT ... FOR UPDATE`` inside the document's own transaction: if the document fails to save, the number
was never used; if two bills are made at once, the second waits for the first to commit.
"""

from datetime import date

from sqlalchemy import BigInteger, CheckConstraint, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from app.core.context import Ctx
from app.core.db import Base, IdMixin, TenantMixin
from app.core.ids import uuid7

MAX_LENGTH = 16


def financial_year(year: int, month: int) -> str:
    """Indian financial year (April to March) as 'YY-YY': April 2026 to March 2027 is '26-27'."""
    start = year if month >= 4 else year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


class BillSequence(IdMixin, TenantMixin, Base):
    __tablename__ = "bill_sequences"
    __table_args__ = (
        UniqueConstraint("business_id", "fy", "series"),
        CheckConstraint("next_number >= 1", name="next_number"),
    )

    fy: Mapped[str] = mapped_column(String(5))
    series: Mapped[str] = mapped_column(String(3))
    next_number: Mapped[int] = mapped_column(BigInteger, default=1)


async def next_number(ctx: Ctx, series: str, on_date: date) -> tuple[str, str, int]:
    """Return (document number, financial year, sequence) and advance the counter. Call inside the document's txn."""
    fy = financial_year(on_date.year, on_date.month)
    await ctx.db.execute(
        insert(BillSequence)
        .values(id=uuid7(), business_id=ctx.tenant.business_id, fy=fy, series=series, next_number=1)
        .on_conflict_do_nothing(index_elements=["business_id", "fy", "series"])
    )
    row = await ctx.db.scalar(
        select(BillSequence).where(BillSequence.fy == fy, BillSequence.series == series).with_for_update()
    )
    if row is None:  # pragma: no cover - the insert above guarantees the row
        raise RuntimeError("bill sequence row missing")
    seq = row.next_number
    row.next_number = seq + 1
    number = f"{fy}/{series}/{seq:06d}"
    if len(number) > MAX_LENGTH:  # 7-digit sequences still fit; beyond 9,999,999 a series must be rolled over
        raise RuntimeError("document number exceeds 16 characters")
    return number, fy, seq
