"""Printable bills: text rules (fast, no PDF engine) and real PDF output."""

import shutil
import subprocess
from typing import Any

import pytest

from app.modules.sales.pdf import money, quantity, render_html
from app.modules.sales.schemas import BillLineOut, BillOut
from tests import factory
from tests.conftest import make_business
from tests.test_sales import GSTIN_KA, GSTIN_TN, _shop


def test_money_uses_indian_grouping() -> None:
    assert money(0) == "0"
    assert money(56_250) == "562.50"
    assert money(100) == "1"
    assert money(123_456_789) == "12,34,567.89"
    assert money(1_000_000) == "10,000"
    assert money(-9_900) == "-99"


def _line(**over: Any) -> BillLineOut:
    base: dict[str, Any] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "line_no": 1,
        "product_id": "00000000-0000-0000-0000-000000000002",
        "variety_id": None,
        "grade_id": None,
        "unit_id": "00000000-0000-0000-0000-000000000003",
        "description": "Banana · Robusta",
        "description_ta": "வாழைப்பழம் · ரோபஸ்டா",
        "hsn_code": "0803",
        "unit_code": "kg",
        "unit_base_factor": 1000,
        "quantity_base": 12_500,
        "unit_price_paise": 4_500,
        "gst_rate_bp": 500,
        "taxable_paise": 56_250,
        "cgst_paise": 1_406,
        "sgst_paise": 1_406,
        "igst_paise": 0,
        "total_paise": 59_062,
    }
    return BillLineOut(**{**base, **over})


def _bill(**over: Any) -> BillOut:
    base: dict[str, Any] = {
        "id": "00000000-0000-0000-0000-0000000000aa",
        "bill_number": "26-27/S/000007",
        "doc_type": "tax_invoice",
        "bill_date": "2026-09-28",
        "status": "active",
        "location_id": "00000000-0000-0000-0000-0000000000bb",
        "party_id": None,
        "party_name": "Raja <script>alert(1)</script> & Sons",
        "total_paise": 59_100,
        "paid_paise": 50_000,
        "created_at": "2026-09-28T10:00:00Z",
        "series": "S",
        "party_phone": "9000000001",
        "party_gstin": None,
        "party_address": None,
        "seller_name": "ABC Banana Traders",
        "seller_gstin": GSTIN_TN,
        "seller_address": "Koyambedu Market, Chennai",
        "seller_phone": None,
        "place_of_supply": "33",
        "supply_type": "intra",
        "taxable_paise": 56_250,
        "cgst_paise": 1_406,
        "sgst_paise": 1_406,
        "igst_paise": 0,
        "round_off_paise": 38,
        "credit_paise": 9_100,
        "void_reason": None,
        "voided_at": None,
        "note": None,
        "created_by": "00000000-0000-0000-0000-0000000000cc",
        "lines": [_line()],
        "payments": [],
    }
    return BillOut(**{**base, **over})


def test_quantity_is_shown_in_the_unit_it_was_priced_in() -> None:
    assert quantity(_line()) == "12.5 kg"
    assert quantity(_line(quantity_base=750)) == "0.75 kg"
    assert quantity(_line(quantity_base=3, unit_base_factor=1, unit_code="piece")) == "3 piece"
    assert quantity(_line(quantity_base=1, unit_base_factor=3)) == "0.333 kg"


def test_tax_invoice_html_shows_the_gst_split_and_escapes_user_text() -> None:
    html = render_html(_bill())
    assert "TAX INVOICE" in html and "26-27/S/000007" in html and GSTIN_TN in html
    assert "CGST" in html and "SGST" in html and "IGST" not in html.split("<tbody>", 2)[-1]
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp; Sons" in html
    assert "Round off" in html and "+0.38" in html and "On credit" in html
    assert "28-09-2026" in html and "Place of supply" in html


def test_inter_state_bill_shows_igst_only() -> None:
    html = render_html(
        _bill(
            supply_type="inter",
            place_of_supply="29",
            cgst_paise=0,
            sgst_paise=0,
            igst_paise=2_812,
            party_gstin=GSTIN_KA,
        )
    )
    totals = html.split('class="totals"', 1)[1]
    assert "IGST" in totals and "CGST" not in totals and "SGST" not in totals


def test_bill_of_supply_and_cancelled_bill() -> None:
    plain = render_html(
        _bill(
            doc_type="bill_of_supply", seller_gstin=None, cgst_paise=0, sgst_paise=0, round_off_paise=0, credit_paise=0
        )
    )
    assert "BILL OF SUPPLY" in plain and "exempt from GST" in plain and "CGST" not in plain
    void = render_html(_bill(status="void"))
    assert "CANCELLED" in void and "CANCELLED" not in render_html(_bill())


def test_tamil_bill_uses_tamil_labels_and_names() -> None:
    html = render_html(_bill(), lang="ta")
    assert "வரி விலைப்பட்டியல்" in html and "வாழைப்பழம் · ரோபஸ்டா" in html and "பில் எண்" in html
    assert 'lang="ta"' in html and "Noto Sans Tamil" in html


def test_thermal_layout_is_narrow_and_compact() -> None:
    thermal = render_html(_bill(), fmt="thermal")
    assert "80mm" in thermal and "HSN" not in thermal
    assert "A4" in render_html(_bill(), fmt="a4") and "HSN" in render_html(_bill(), fmt="a4")


async def test_pdf_download_for_a4_and_thermal(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory, gstin=GSTIN_TN)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 12_500, 45)], payments=[{"method": "cash", "amount_paise": 56_300}]
    )
    a4 = await a.get(f"/api/w/bills/{bill['id']}/pdf")
    assert a4.status_code == 200 and a4.headers["content-type"] == "application/pdf"
    assert a4.content.startswith(b"%PDF") and len(a4.content) > 1_000
    assert bill["bill_number"].replace("/", "-") in a4.headers["content-disposition"]
    assert a4.headers["cache-control"] == "private, no-store"
    thermal = await a.get(f"/api/w/bills/{bill['id']}/pdf", params={"format": "thermal"})
    assert thermal.content.startswith(b"%PDF") and thermal.content != a4.content
    assert (await a.get(f"/api/w/bills/{bill['id']}/pdf", params={"format": "poster"})).status_code == 422


def _installed_tamil_font() -> str:
    """The font fontconfig picks for Tamil text: the bill asks for "Noto Sans Tamil", so this machine must have one."""
    fc_match = shutil.which("fc-match")
    if fc_match is None:
        pytest.skip("fontconfig is not installed here")
    result = subprocess.run(  # noqa: S603  # fixed arguments, no user input
        [fc_match, "Noto Sans Tamil:lang=ta", "-f", "%{family}"], capture_output=True, text=True, check=True
    )
    return result.stdout


async def test_tamil_pdf_embeds_a_tamil_font(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    pdf = (await a.get(f"/api/w/bills/{bill['id']}/pdf", params={"lang": "ta"})).content
    assert pdf.startswith(b"%PDF")
    match = _installed_tamil_font()
    assert "Tamil" in match, f"no Tamil font installed (fontconfig chose {match!r})"


async def test_pdf_respects_tenancy_and_permissions(admin_client: Any, client_factory: Any) -> None:
    a, business_id, shop, banana, kg = await _shop(admin_client, client_factory)
    b, *_ = await _shop(admin_client, client_factory)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    assert (await b.get(f"/api/w/bills/{bill['id']}/pdf")).status_code == 404
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    stock_staff, _ = await make_business(admin_client, client_factory, role="stock", business_id=business_id)
    assert (await viewer.get(f"/api/w/bills/{bill['id']}/pdf")).status_code == 200
    assert (await stock_staff.get(f"/api/w/bills/{bill['id']}/pdf")).status_code == 403
