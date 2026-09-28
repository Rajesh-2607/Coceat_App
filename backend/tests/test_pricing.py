"""Bill arithmetic: rounding and GST rules (pure functions, no database)."""

import pytest

from app.core.numbering import financial_year
from app.modules.sales.pricing import LineInput, bill_totals, line_amount, line_tax, price_line, round_to_rupee


def test_line_amount_rounds_half_up_per_line() -> None:
    assert line_amount(quantity_base=12_500, base_factor=1_000, unit_price_paise=4_500) == 56_250  # 12.5 kg x Rs 45
    assert line_amount(1, 1_000, 4_500) == 5  # 1 g at Rs 45/kg = 4.5 paise -> 5
    assert line_amount(1, 1_000, 4_400) == 4  # 4.4 -> 4
    assert line_amount(3, 3, 999) == 999  # whole units
    assert line_amount(0, 1_000, 5_000) == 0


def test_gst_intra_state_splits_equally() -> None:
    assert line_tax(10_000, 500, inter_state=False) == (250, 250, 0)  # 5% on Rs 100
    cgst, sgst, igst = line_tax(1_001, 500, inter_state=False)  # half rate 2.5% of 10.01 = 0.25025 -> 25
    assert cgst == sgst == 25 and igst == 0
    assert line_tax(10_000, 0, inter_state=False) == (0, 0, 0)


def test_gst_inter_state_is_all_igst() -> None:
    assert line_tax(10_000, 1800, inter_state=True) == (0, 0, 1_800)
    assert line_tax(333, 500, inter_state=True) == (0, 0, 17)  # 16.65 -> 17


@pytest.mark.parametrize(
    ("paise", "expected"),
    [(0, 0), (49, 0), (50, 100), (99, 100), (100, 100), (149, 100), (150, 200), (1_234_567, 1_234_600)],
)
def test_round_to_rupee_half_up(paise: int, expected: int) -> None:
    assert round_to_rupee(paise) == expected


def test_bill_totals_round_off_is_shown_and_balances() -> None:
    lines = [
        price_line(LineInput(12_500, 1_000, 4_500, 0), inter_state=False),  # 562.50 exempt
        price_line(LineInput(2, 1, 1_999, 500), inter_state=False),  # 39.98 with 5% GST
    ]
    totals = bill_totals(lines)
    exact = totals.taxable_paise + totals.cgst_paise + totals.sgst_paise + totals.igst_paise
    assert totals.total_paise % 100 == 0
    assert totals.total_paise == exact + totals.round_off_paise
    assert abs(totals.round_off_paise) < 100
    assert totals.cgst_paise == totals.sgst_paise


def test_total_of_lines_never_drifts_from_sum_of_line_totals() -> None:
    results = [price_line(LineInput(q, 1_000, 3_333, 1200), inter_state=False) for q in (250, 333, 777, 1_001)]
    totals = bill_totals(results)
    assert totals.taxable_paise + totals.cgst_paise + totals.sgst_paise == sum(r.total_paise for r in results)


def test_financial_year_runs_april_to_march() -> None:
    assert financial_year(2026, 4) == "26-27"
    assert financial_year(2027, 3) == "26-27"
    assert financial_year(2027, 4) == "27-28"
    assert financial_year(2026, 1) == "25-26"
    assert financial_year(2099, 12) == "99-00"
