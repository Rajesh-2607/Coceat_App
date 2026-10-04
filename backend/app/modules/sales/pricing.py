"""Bill arithmetic. Pure integer maths in paise: no floats, no Decimal, no database.

Rules (agreed with the business, legally sensitive: change only with sign-off):
- a line amount is ``unit_price * quantity / base_factor`` rounded half-up to a whole paisa, per line;
- GST is charged per line on that taxable amount, rounded half-up per line, added on top (prices are tax-exclusive);
- within the state the rate splits equally into CGST and SGST (each rounded on its own half rate, so they are
  always equal); across states the whole rate is IGST;
- the bill total is rounded half-up to the whole rupee and the difference is shown as ``round_off``.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# 0%, 0.25%, 3%, 5%, 12%, 18%, 28% (GST slabs), in basis points
ALLOWED_GST_RATES_BP: frozenset[int] = frozenset({0, 25, 300, 500, 1200, 1800, 2800})


def line_amount(quantity_base: int, base_factor: int, unit_price_paise: int) -> int:
    """Taxable value of a line in paise, rounded half-up."""
    numerator = unit_price_paise * quantity_base
    return (numerator + base_factor // 2) // base_factor


def line_tax(taxable_paise: int, rate_bp: int, *, inter_state: bool) -> tuple[int, int, int]:
    """(cgst, sgst, igst) in paise for one line."""
    if rate_bp == 0:
        return 0, 0, 0
    if inter_state:
        return 0, 0, (taxable_paise * rate_bp + 5_000) // 10_000
    half = (taxable_paise * rate_bp + 10_000) // 20_000  # half the rate, rounded half-up
    return half, half, 0


def round_to_rupee(paise: int) -> int:
    """Nearest whole rupee in paise (half rounds up). Bills are never negative."""
    return ((paise + 50) // 100) * 100


@dataclass(frozen=True, slots=True)
class LineInput:
    quantity_base: int
    base_factor: int
    unit_price_paise: int
    gst_rate_bp: int


@dataclass(frozen=True, slots=True)
class LineResult:
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int

    @property
    def total_paise(self) -> int:
        return self.taxable_paise + self.cgst_paise + self.sgst_paise + self.igst_paise


@dataclass(frozen=True, slots=True)
class Totals:
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    round_off_paise: int
    total_paise: int  # what the customer pays: whole rupees


def price_line(line: LineInput, *, inter_state: bool) -> LineResult:
    taxable = line_amount(line.quantity_base, line.base_factor, line.unit_price_paise)
    cgst, sgst, igst = line_tax(taxable, line.gst_rate_bp, inter_state=inter_state)
    return LineResult(taxable, cgst, sgst, igst)


def bill_totals(results: Sequence[LineResult]) -> Totals:
    taxable = sum(r.taxable_paise for r in results)
    cgst = sum(r.cgst_paise for r in results)
    sgst = sum(r.sgst_paise for r in results)
    igst = sum(r.igst_paise for r in results)
    exact = taxable + cgst + sgst + igst
    total = round_to_rupee(exact)
    return Totals(taxable, cgst, sgst, igst, total - exact, total)
