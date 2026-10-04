"""Billing: numbering, GST, atomic effects (stock, ledger, payments), void, returns, roles and isolation."""

import asyncio
from typing import Any

import psycopg
import pytest

from app.core.numbering import financial_year
from app.modules.sales.service import today_ist
from tests import factory
from tests.conftest import app_conn, idem, make_business, superuser_conn

GSTIN_TN = "33ABCDE1234F1Z5"  # Tamil Nadu (state code 33)
GSTIN_KA = "29ABCDE1234F1Z5"  # Karnataka (29)


def _prefix() -> str:
    today = today_ist()
    return financial_year(today.year, today.month)


async def _shop(admin_client: Any, client_factory: Any, *, gstin: str | None = None, **kwargs: Any) -> tuple[Any, ...]:
    """A business with a shop that holds 100 kg of banana (Rs 45/kg, exempt) and a kg unit."""
    owner, business_id = await make_business(admin_client, client_factory, **kwargs)
    if gstin:
        r = await admin_client.patch(f"/api/admin/businesses/{business_id}", json={"gstin": gstin})
        assert r.status_code == 200, r.text
    shop = await factory.location(owner, "Shop")
    banana = await factory.product(owner, "Banana", default_price_paise=4500)
    await factory.opening(owner, shop["id"], banana["id"], 100_000)
    kg = await factory.unit(owner, "kg")
    return owner, business_id, shop, banana, kg


async def test_cash_sale_of_exempt_goods_is_a_bill_of_supply(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 12_500, 45)], payments=[{"method": "cash", "amount_paise": 56_300}]
    )
    assert bill["bill_number"] == f"{_prefix()}/S/000001" and len(bill["bill_number"]) <= 16
    assert bill["doc_type"] == "bill_of_supply" and bill["status"] == "active"
    assert bill["taxable_paise"] == 56_250 and bill["round_off_paise"] == 50 and bill["total_paise"] == 56_300
    assert bill["cgst_paise"] == bill["sgst_paise"] == bill["igst_paise"] == 0
    assert bill["paid_paise"] == 56_300 and bill["credit_paise"] == 0 and bill["party_id"] is None
    assert bill["lines"][0]["description"] == "Banana" and bill["lines"][0]["total_paise"] == 56_250
    assert [(p["method"], p["amount_paise"], p["direction"]) for p in bill["payments"]] == [("cash", 56_300, "in")]
    assert await factory.stock_of(a, banana, shop) == 87_500  # 100 kg - 12.5 kg
    assert (await a.get(f"/api/w/bills/{bill['id']}")).json()["bill_number"] == bill["bill_number"]


async def test_bill_numbers_are_sequential_and_a_failed_bill_leaves_no_gap(
    admin_client: Any, client_factory: Any
) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    pay = [{"method": "cash", "amount_paise": 45_000}]
    first = await factory.sell(a, shop, [factory.line(banana, kg, 1_000, 450)], payments=pay)
    too_much = [factory.line(banana, kg, 500_000, 45)]  # 500 kg from a shop holding 99 kg
    failed = await factory.sell(a, shop, too_much, expect=422, payments=[{"method": "cash", "amount_paise": 2_250_000}])
    assert failed["code"] == "insufficient_stock"
    second = await factory.sell(a, shop, [factory.line(banana, kg, 1_000, 450)], payments=pay)
    assert first["bill_number"].endswith("/S/000001") and second["bill_number"].endswith("/S/000002")
    assert await factory.stock_of(a, banana, shop) == 98_000  # only the two real bills left the shop


async def test_concurrent_bills_get_distinct_consecutive_numbers(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    body = {
        "location_id": shop["id"],
        "lines": [factory.line(banana, kg, 1_000, 45)],
        "payments": [{"method": "cash", "amount_paise": 4_500}],
    }
    results = await asyncio.gather(*(a.post("/api/w/bills", json=body, headers=idem()) for _ in range(6)))
    assert {r.status_code for r in results} == {201}
    numbers = sorted(r.json()["bill_number"] for r in results)
    assert [n.rsplit("/", 1)[1] for n in numbers] == [f"{i:06d}" for i in range(1, 7)]
    assert await factory.stock_of(a, banana, shop) == 94_000


async def test_tax_invoice_splits_gst_into_cgst_and_sgst_within_the_state(
    admin_client: Any, client_factory: Any
) -> None:
    a, _, shop, _, kg = await _shop(admin_client, client_factory, gstin=GSTIN_TN)
    jaggery = await factory.product(a, "Jaggery", gst_rate_bp=500, hsn_code="1701")
    await factory.opening(a, shop["id"], jaggery["id"], 50_000)
    bill = await factory.sell(
        a, shop, [factory.line(jaggery, kg, 2_000, 100)], payments=[{"method": "upi", "amount_paise": 21_000}]
    )
    assert bill["doc_type"] == "tax_invoice" and bill["supply_type"] == "intra" and bill["place_of_supply"] == "33"
    assert (bill["taxable_paise"], bill["cgst_paise"], bill["sgst_paise"], bill["igst_paise"]) == (20_000, 500, 500, 0)
    assert bill["total_paise"] == 21_000 and bill["round_off_paise"] == 0 and bill["seller_gstin"] == GSTIN_TN
    assert bill["lines"][0]["hsn_code"] == "1701" and bill["lines"][0]["gst_rate_bp"] == 500


async def test_sale_to_a_customer_in_another_state_charges_igst(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, kg = await _shop(admin_client, client_factory, gstin=GSTIN_TN)
    jaggery = await factory.product(a, "Jaggery", gst_rate_bp=500)
    await factory.opening(a, shop["id"], jaggery["id"], 50_000)
    buyer = await factory.customer(a, "Bengaluru Traders", gstin=GSTIN_KA)
    bill = await factory.sell(
        a,
        shop,
        [factory.line(jaggery, kg, 2_000, 100)],
        party_id=buyer["id"],
        payments=[{"method": "bank", "amount_paise": 21_000}],
    )
    assert bill["supply_type"] == "inter" and bill["place_of_supply"] == "29"
    assert (bill["cgst_paise"], bill["sgst_paise"], bill["igst_paise"]) == (0, 0, 1_000)
    assert bill["party_gstin"] == GSTIN_KA and bill["party_name"] == "Bengaluru Traders"
    # a walk-in can be billed for another state by naming the place of supply
    walk_in = await factory.sell(
        a,
        shop,
        [factory.line(jaggery, kg, 1_000, 100)],
        place_of_supply="29",
        payments=[{"method": "cash", "amount_paise": 10_500}],
    )
    assert walk_in["igst_paise"] == 500 and walk_in["cgst_paise"] == 0


async def test_business_without_gstin_cannot_charge_gst(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, kg = await _shop(admin_client, client_factory)
    taxed = await factory.product(a, "Packed dates", gst_rate_bp=1200)
    await factory.opening(a, shop["id"], taxed["id"], 10_000)
    r = await factory.sell(a, shop, [factory.line(taxed, kg, 1_000, 200)], expect=422)
    assert r["code"] == "gst_needs_gstin"
    assert await factory.stock_of(a, taxed, shop) == 10_000  # nothing was taken


async def test_registered_business_selling_only_exempt_goods_issues_a_bill_of_supply(
    admin_client: Any, client_factory: Any
) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory, gstin=GSTIN_TN)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    assert bill["doc_type"] == "bill_of_supply" and bill["seller_gstin"] == GSTIN_TN


async def test_credit_sale_goes_on_the_customers_account(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    c = await factory.customer(a, "Anand Hotel", credit_limit_paise=100_000, opening_balance_paise=10_000)
    bill = await factory.sell(
        a,
        shop,
        [factory.line(banana, kg, 20_000, 45)],  # Rs 900
        party_id=c["id"],
        payments=[{"method": "cash", "amount_paise": 30_000}],
    )
    assert bill["total_paise"] == 90_000 and bill["paid_paise"] == 30_000 and bill["credit_paise"] == 60_000
    assert await factory.party_balance(a, "customers", c["id"]) == 10_000 + 60_000
    kinds = [e["entry_type"] for e in (await a.get(f"/api/w/customers/{c['id']}/ledger")).json()]
    assert kinds == ["payment_in", "sale", "opening"]  # newest first


async def test_credit_rules(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    c = await factory.customer(a, "Small Shop", credit_limit_paise=100_000)
    one_kg = [factory.line(banana, kg, 20_000, 45)]  # Rs 900
    assert (await factory.sell(a, shop, one_kg, expect=422))["code"] == "credit_needs_customer"
    ok = await factory.sell(a, shop, one_kg, party_id=c["id"])
    assert ok["credit_paise"] == 90_000
    r = await factory.sell(a, shop, one_kg, party_id=c["id"], expect=422)  # 900 + 900 > limit of 1000
    assert r["code"] == "credit_limit_exceeded"
    r = await factory.sell(a, shop, one_kg, expect=422, payments=[{"method": "cash", "amount_paise": 99_999_00}])
    assert r["code"] == "overpaid"
    r = await factory.sell(a, shop, [factory.line(banana, kg, 1_000, 0)], expect=422)
    assert r["code"] == "zero_total"
    assert await factory.party_balance(a, "customers", c["id"]) == 90_000


async def test_void_restores_stock_ledger_and_payments_but_keeps_the_number(
    admin_client: Any, client_factory: Any
) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    c = await factory.customer(a, "Raja", opening_balance_paise=5_000)
    bill = await factory.sell(
        a,
        shop,
        [factory.line(banana, kg, 10_000, 45)],
        party_id=c["id"],
        payments=[{"method": "cash", "amount_paise": 20_000}],
    )
    assert await factory.stock_of(a, banana, shop) == 90_000
    assert await factory.party_balance(a, "customers", c["id"]) == 5_000 + 25_000

    r = await a.post(f"/api/w/bills/{bill['id']}/void", json={"reason": "wrong customer"}, headers=idem())
    assert r.status_code == 200, r.text
    voided = r.json()
    assert voided["status"] == "void" and voided["void_reason"] == "wrong customer" and voided["voided_at"]
    assert voided["bill_number"] == bill["bill_number"]
    assert await factory.stock_of(a, banana, shop) == 100_000
    assert await factory.party_balance(a, "customers", c["id"]) == 5_000
    assert sorted((p["direction"], p["amount_paise"]) for p in voided["payments"]) == [("in", 20_000), ("out", 20_000)]

    again = await a.post(f"/api/w/bills/{bill['id']}/void", json={"reason": "again"}, headers=idem())
    assert again.status_code == 409 and again.json()["code"] == "already_void"
    # the next bill continues the sequence: a cancelled bill's number is never reused
    nxt = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    assert nxt["bill_number"].endswith("/S/000002")
    listed = (await a.get("/api/w/bills", params={"status": "void"})).json()
    assert [b["bill_number"] for b in listed] == [bill["bill_number"]]


async def test_return_restocks_credits_the_party_and_refunds(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    c = await factory.customer(a, "Lakshmi Stores")
    bill = await factory.sell(a, shop, [factory.line(banana, kg, 10_000, 50)], party_id=c["id"])  # Rs 500 on credit
    line_id = bill["lines"][0]["id"]
    body = {
        "lines": [{"bill_line_id": line_id, "quantity": 4_000}],
        "reason": "overripe",
        "refund_paise": 5_000,
        "refund_method": "cash",
    }
    ret = (await a.post(f"/api/w/bills/{bill['id']}/returns", json=body, headers=idem())).json()
    assert ret["return_number"].endswith("/R/000001") and ret["total_paise"] == 20_000 and ret["refund_paise"] == 5_000
    assert await factory.stock_of(a, banana, shop) == 90_000 + 4_000
    # she owed 500; goods worth 200 came back and Rs 50 of it was paid back in cash: 500 - 200 + 50
    assert await factory.party_balance(a, "customers", c["id"]) == 50_000 - 20_000 + 5_000
    detail = (await a.get(f"/api/w/bills/{bill['id']}")).json()
    assert detail["lines"][0]["returned_base"] == 4_000
    assert len((await a.get(f"/api/w/bills/{bill['id']}/returns")).json()) == 1

    too_many = {**body, "lines": [{"bill_line_id": line_id, "quantity": 6_001}], "refund_paise": 0}
    r = await a.post(f"/api/w/bills/{bill['id']}/returns", json=too_many, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "return_exceeds_sold"
    rest = {**body, "lines": [{"bill_line_id": line_id, "quantity": 6_000}], "refund_paise": 0}
    assert (await a.post(f"/api/w/bills/{bill['id']}/returns", json=rest, headers=idem())).status_code == 201
    # a bill with returns can no longer be cancelled
    r = await a.post(f"/api/w/bills/{bill['id']}/void", json={"reason": "too late"}, headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "has_returns"


async def test_return_options_and_walk_in_rules(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 10_000, 45)], payments=[{"method": "cash", "amount_paise": 45_000}]
    )
    line_id = bill["lines"][0]["id"]
    base = {"lines": [{"bill_line_id": line_id, "quantity": 2_000}], "reason": "bad quality"}
    r = await a.post(f"/api/w/bills/{bill['id']}/returns", json=base, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "walk_in_needs_full_refund"
    r = await a.post(f"/api/w/bills/{bill['id']}/returns", json={**base, "refund_paise": 9_000}, headers=idem())
    assert r.json()["code"] == "refund_method_required"
    dead = {**base, "refund_paise": 9_000, "refund_method": "cash", "restock": False}
    assert (await a.post(f"/api/w/bills/{bill['id']}/returns", json=dead, headers=idem())).status_code == 201
    assert await factory.stock_of(a, banana, shop) == 90_000  # spoiled goods are not put back on the shelf
    await a.post(f"/api/w/bills/{bill['id']}/void", json={"reason": "x"}, headers=idem())  # refused: has returns
    voided = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    await a.post(f"/api/w/bills/{voided['id']}/void", json={"reason": "mistake"}, headers=idem())
    r = await a.post(
        f"/api/w/bills/{voided['id']}/returns",
        json={**base, "lines": [{"bill_line_id": voided["lines"][0]["id"], "quantity": 1}]},
        headers=idem(),
    )
    assert r.status_code == 422 and r.json()["code"] == "bill_void"


async def test_idempotent_bill_creation_bills_once(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    body = {
        "location_id": shop["id"],
        "lines": [factory.line(banana, kg, 5_000, 45)],
        "payments": [{"method": "cash", "amount_paise": 22_500}],
    }
    headers = idem()
    first = await a.post("/api/w/bills", json=body, headers=headers)
    again = await a.post("/api/w/bills", json=body, headers=headers)
    assert first.status_code == again.status_code == 201 and first.json() == again.json()
    assert again.headers.get("idempotent-replayed") == "true"
    assert len((await a.get("/api/w/bills")).json()) == 1
    assert await factory.stock_of(a, banana, shop) == 95_000


async def test_bills_are_isolated_between_businesses(admin_client: Any, client_factory: Any) -> None:
    a, _, shop_a, banana_a, kg_a = await _shop(admin_client, client_factory)
    b, _, shop_b, banana_b, kg_b = await _shop(admin_client, client_factory)
    party_a = await factory.customer(a, "A customer")
    bill = await factory.sell(
        a, shop_a, [factory.line(banana_a, kg_a, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    assert (await b.get(f"/api/w/bills/{bill['id']}")).status_code == 404
    assert (await b.post(f"/api/w/bills/{bill['id']}/void", json={"reason": "nope"}, headers=idem())).status_code == 404
    assert (await b.get(f"/api/w/bills/{bill['id']}/returns")).status_code == 404
    assert (await b.get("/api/w/bills")).json() == []
    # B cannot bill using A's location, product, unit or customer
    pay = [{"method": "cash", "amount_paise": 4_500}]
    assert (await factory.sell(b, shop_a, [factory.line(banana_b, kg_b, 1_000, 45)], expect=404, payments=pay))[
        "code"
    ] == "not_found"
    await factory.sell(b, shop_b, [factory.line(banana_a, kg_b, 1_000, 45)], expect=404, payments=pay)
    await factory.sell(b, shop_b, [factory.line(banana_b, kg_a, 1_000, 45)], expect=422, payments=pay)
    await factory.sell(
        b, shop_b, [factory.line(banana_b, kg_b, 1_000, 45)], expect=404, party_id=party_a["id"], payments=pay
    )
    assert await factory.stock_of(a, banana_a, shop_a) == 99_000


async def test_roles_and_module_gates_on_billing(admin_client: Any, client_factory: Any) -> None:
    owner, business_id, shop, banana, kg = await _shop(admin_client, client_factory)
    billing, _ = await make_business(admin_client, client_factory, role="billing", business_id=business_id)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    stock_staff, _ = await make_business(admin_client, client_factory, role="stock", business_id=business_id)
    pay = [{"method": "cash", "amount_paise": 4_500}]
    mine = await factory.sell(
        billing, shop, [factory.line(banana, kg, 1_000, 45)], payments=pay
    )  # counter staff may bill
    assert (await viewer.get(f"/api/w/bills/{mine['id']}")).status_code == 200
    r = await factory.sell(viewer, shop, [factory.line(banana, kg, 1_000, 45)], expect=403, payments=pay)
    assert r["code"] == "permission_denied"
    await factory.sell(stock_staff, shop, [factory.line(banana, kg, 1_000, 45)], expect=403, payments=pay)
    # counter staff cannot cancel; the owner can
    r = await billing.post(f"/api/w/bills/{mine['id']}/void", json={"reason": "oops"}, headers=idem())
    assert r.status_code == 403
    assert (
        await owner.post(f"/api/w/bills/{mine['id']}/void", json={"reason": "oops"}, headers=idem())
    ).status_code == 200
    no_sell, _ = await make_business(admin_client, client_factory, modules=["bills", "stock"])
    loc = await factory.location(no_sell, "Shop")
    p = await factory.product(no_sell, "Banana")
    u = await factory.unit(no_sell, "kg")
    await factory.opening(no_sell, loc["id"], p["id"], 10_000)
    assert (await factory.sell(no_sell, loc, [factory.line(p, u, 1_000, 45)], expect=403, payments=pay))[
        "code"
    ] == "module_disabled"
    assert (await no_sell.get("/api/w/bills")).status_code == 200  # viewing needs only the bills module


async def test_restricted_staff_only_bill_from_their_own_location(admin_client: Any, client_factory: Any) -> None:
    owner, business_id, shop, banana, kg = await _shop(admin_client, client_factory)
    other = await factory.location(owner, "Other shop")
    await factory.opening(owner, other["id"], banana["id"], 10_000)
    staff, _ = await make_business(
        admin_client, client_factory, role="billing", business_id=business_id, location_ids=[shop["id"]]
    )
    pay = [{"method": "cash", "amount_paise": 4_500}]
    await factory.sell(staff, other, [factory.line(banana, kg, 1_000, 45)], expect=404, payments=pay)
    here = await factory.sell(staff, shop, [factory.line(banana, kg, 1_000, 45)], payments=pay)
    elsewhere = await factory.sell(owner, other, [factory.line(banana, kg, 1_000, 45)], payments=pay)
    assert [b["id"] for b in (await staff.get("/api/w/bills")).json()] == [here["id"]]
    assert (await staff.get(f"/api/w/bills/{elsewhere['id']}")).status_code == 404


async def test_bill_search_and_filters(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg = await _shop(admin_client, client_factory)
    c = await factory.customer(a, "Chennai Fresh Mart", phone="9000001001")
    one = await factory.sell(a, shop, [factory.line(banana, kg, 1_000, 45)], party_id=c["id"])
    two = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    by_name = (await a.get("/api/w/bills", params={"q": "fresh"})).json()
    assert [b["id"] for b in by_name] == [one["id"]]
    assert [b["id"] for b in (await a.get("/api/w/bills", params={"q": two["bill_number"]})).json()] == [two["id"]]
    assert [b["id"] for b in (await a.get("/api/w/bills", params={"party_id": c["id"]})).json()] == [one["id"]]
    assert (await a.get("/api/w/bills", params={"date_from": "2999-01-01"})).json() == []
    page = (await a.get("/api/w/bills", params={"limit": 1})).json()
    assert [b["id"] for b in page] == [two["id"]]
    rest = (await a.get("/api/w/bills", params={"limit": 5, "before_id": page[-1]["id"]})).json()
    assert [b["id"] for b in rest] == [one["id"]]


async def test_bills_cannot_be_edited_or_deleted_even_by_a_superuser(admin_client: Any, client_factory: Any) -> None:
    a, business_a, shop, banana, kg = await _shop(admin_client, client_factory)
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    with app_conn() as conn:
        for stmt in ("DELETE FROM bills", "DELETE FROM bill_lines", "UPDATE bill_lines SET quantity_base = 1"):
            conn.execute("SELECT set_config('app.business_id', %s, true)", (business_a,))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(stmt)  # type: ignore[arg-type]
            conn.rollback()
    with superuser_conn() as conn:
        for stmt in (
            "UPDATE bills SET total_paise = 100",  # not a cancellation
            "UPDATE bills SET status = 'active', note = 'edited'",
            "DELETE FROM bills",
            "UPDATE bill_lines SET quantity_base = 1",
            "TRUNCATE bills CASCADE",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(stmt)  # type: ignore[arg-type]
        # cancelling is the one change allowed, and it needs its reason and time
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE bills SET status = 'void' WHERE id = %s", (bill["id"],))
