"""Reports: day book, sales, GST summary, outstanding balances and wastage."""

from datetime import timedelta
from typing import Any

from app.modules.sales.service import today_ist
from tests import factory
from tests.conftest import idem, make_business

GSTIN_TN = "33ABCDE1234F1Z5"


async def _trading_day(admin_client: Any, client_factory: Any) -> tuple[Any, ...]:
    """Two bills (one exempt, one 5% GST), a part return, a purchase, a credit customer and some wastage."""
    a, business_id = await make_business(admin_client, client_factory)
    await admin_client.patch(f"/api/admin/businesses/{business_id}", json={"gstin": GSTIN_TN})
    shop = await factory.location(a, "Shop")
    banana = await factory.product(a, "Banana")
    jaggery = await factory.product(a, "Jaggery", gst_rate_bp=500)
    kg = await factory.unit(a, "kg")
    supplier = await factory.supplier(a, "Theni Farms")
    for p in (banana, jaggery):
        await factory.opening(a, shop["id"], p["id"], 100_000)

    await factory.sell(
        a, shop, [factory.line(banana, kg, 10_000, 45)], payments=[{"method": "cash", "amount_paise": 45_000}]
    )
    bill = await factory.sell(
        a, shop, [factory.line(jaggery, kg, 2_000, 100)], payments=[{"method": "upi", "amount_paise": 21_000}]
    )
    ret = {
        "lines": [{"bill_line_id": bill["lines"][0]["id"], "quantity": 1_000}],
        "reason": "damaged pack",
        "refund_paise": 10_500,
        "refund_method": "cash",
    }
    assert (await a.post(f"/api/w/bills/{bill['id']}/returns", json=ret, headers=idem())).status_code == 201
    await factory.post(
        a,
        "/api/w/purchases",
        {
            "supplier_id": supplier["id"],
            "location_id": shop["id"],
            "lines": [{"product_id": banana["id"], "unit_id": kg["id"], "quantity": 100_000, "unit_cost_paise": 3_000}],
            "payments": [{"method": "bank", "amount_paise": 100_000}],
        },
    )
    debtor = await factory.customer(a, "Anand Hotel", opening_balance_paise=50_000)
    waste = {"location_id": shop["id"], "product_id": banana["id"], "reason_code": "rotten"}
    await factory.post(a, "/api/w/stock/wastage", {**waste, "quantity": 3_000})
    undone = await factory.post(a, "/api/w/stock/wastage", {**waste, "quantity": 1_000})
    await factory.post(a, f"/api/w/stock/movements/{undone['movement_id']}/reverse", {"reason": "entered twice"})
    return a, business_id, shop, banana, debtor, supplier


async def test_day_book_adds_up_the_days_money(admin_client: Any, client_factory: Any) -> None:
    a, *_ = await _trading_day(admin_client, client_factory)
    book = (await a.get("/api/w/reports/daybook")).json()
    assert book["date"] == today_ist().isoformat()
    assert book["sales"] == {
        "bills": 2,
        "taxable_paise": 65_000,
        "tax_paise": 1_000,
        "total_paise": 66_000,
        "collected_paise": 66_000,
        "returns": 1,
        "returns_paise": 10_500,
    }
    assert book["purchases"] == {"purchases": 1, "total_paise": 300_000, "paid_paise": 100_000}
    by_method = {p["method"]: (p["received_paise"], p["paid_paise"]) for p in book["payments"]}
    assert by_method == {"cash": (45_000, 10_500), "upi": (21_000, 0), "bank": (0, 100_000)}
    yesterday = (today_ist() - timedelta(days=1)).isoformat()
    empty = (await a.get("/api/w/reports/daybook", params={"date": yesterday})).json()
    assert empty["sales"]["bills"] == 0 and empty["payments"] == []


async def test_sales_report_by_day_and_product(admin_client: Any, client_factory: Any) -> None:
    a, _, _, banana, *_ = await _trading_day(admin_client, client_factory)
    today = today_ist().isoformat()
    report = (await a.get("/api/w/reports/sales", params={"from": today, "to": today})).json()
    assert report["totals"]["bills"] == 2 and report["totals"]["total_paise"] == 66_000
    assert report["by_day"] == [{"date": today, "bills": 2, "total_paise": 66_000}]
    by_product = {r["description"]: r for r in report["by_product"]}
    assert by_product["Banana"]["quantity_base"] == 10_000 and by_product["Banana"]["total_paise"] == 45_000
    assert by_product["Jaggery"]["taxable_paise"] == 20_000 and by_product["Jaggery"]["total_paise"] == 21_000
    assert by_product["Banana"]["product_id"] == banana["id"]
    assert [r["description"] for r in report["by_product"]] == ["Banana", "Jaggery"]  # biggest first


async def test_gst_summary_nets_returns_by_rate(admin_client: Any, client_factory: Any) -> None:
    a, *_ = await _trading_day(admin_client, client_factory)
    today = today_ist().isoformat()
    report = (await a.get("/api/w/reports/gst", params={"from": today, "to": today})).json()
    assert report["rows"] == [
        {"gst_rate_bp": 0, "taxable_paise": 45_000, "cgst_paise": 0, "sgst_paise": 0, "igst_paise": 0},
        # Rs 200 sold at 5% (Rs 10 tax) less Rs 100 returned (Rs 5 tax)
        {"gst_rate_bp": 500, "taxable_paise": 10_000, "cgst_paise": 250, "sgst_paise": 250, "igst_paise": 0},
    ]
    assert report["total_tax_paise"] == 500


async def test_outstanding_lists_who_owes_and_whom_we_owe(admin_client: Any, client_factory: Any) -> None:
    a, _, _, _, debtor, supplier = await _trading_day(admin_client, client_factory)
    report = (await a.get("/api/w/reports/outstanding")).json()
    assert [(c["party_id"], c["balance_paise"]) for c in report["customers"]] == [(debtor["id"], 50_000)]
    assert [(s["party_id"], s["balance_paise"]) for s in report["suppliers"]] == [(supplier["id"], -200_000)]
    assert report["owed_to_us_paise"] == 50_000 and report["we_owe_paise"] == 200_000


async def test_wastage_report_ignores_reversed_entries(admin_client: Any, client_factory: Any) -> None:
    a, _, _, banana, *_ = await _trading_day(admin_client, client_factory)
    today = today_ist().isoformat()
    report = (await a.get("/api/w/reports/wastage", params={"from": today, "to": today})).json()
    assert report["rows"] == [{"reason_code": "rotten", "product_id": banana["id"], "quantity_base": 3_000}]


async def test_report_ranges_roles_and_module_gate(admin_client: Any, client_factory: Any) -> None:
    a, business_id, *_ = await _trading_day(admin_client, client_factory)
    today = today_ist()
    r = await a.get(
        "/api/w/reports/sales", params={"from": today.isoformat(), "to": (today - timedelta(days=1)).isoformat()}
    )
    assert r.status_code == 422 and r.json()["code"] == "bad_range"
    r = await a.get(
        "/api/w/reports/gst", params={"from": (today - timedelta(days=400)).isoformat(), "to": today.isoformat()}
    )
    assert r.status_code == 422
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    billing, _ = await make_business(admin_client, client_factory, role="billing", business_id=business_id)
    assert (await viewer.get("/api/w/reports/outstanding")).status_code == 200
    assert (await billing.get("/api/w/reports/outstanding")).json()["code"] == "permission_denied"
    no_reports, _ = await make_business(admin_client, client_factory, modules=["sell", "bills"])
    assert (await no_reports.get("/api/w/reports/daybook")).json()["code"] == "module_disabled"


async def test_reports_show_only_the_own_business(admin_client: Any, client_factory: Any) -> None:
    await _trading_day(admin_client, client_factory)
    other, _ = await make_business(admin_client, client_factory)
    today = today_ist().isoformat()
    sales = (await other.get("/api/w/reports/sales", params={"from": today, "to": today})).json()
    assert sales["totals"]["bills"] == 0 and sales["by_product"] == []
    assert (await other.get("/api/w/reports/outstanding")).json()["customers"] == []
    assert (await other.get("/api/w/reports/daybook")).json()["payments"] == []
