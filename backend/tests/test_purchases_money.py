"""Buy / Receive and Money: purchases, supplier accounts, stand-alone payments and their reversal."""

from datetime import timedelta
from typing import Any

from app.modules.sales.service import today_ist
from tests import factory
from tests.conftest import idem, make_business


async def _setup(admin_client: Any, client_factory: Any, **kwargs: Any) -> tuple[Any, ...]:
    owner, business_id = await make_business(admin_client, client_factory, **kwargs)
    shop = await factory.location(owner, "Shop")
    banana = await factory.product(owner, "Banana")
    kg = await factory.unit(owner, "kg")
    supplier = await factory.supplier(owner, "Theni Farms")
    return owner, business_id, shop, banana, kg, supplier


def _purchase(
    shop: dict[str, Any], supplier: dict[str, Any], lines: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    lines = [
        {**{k: v for k, v in ln.items() if k != "unit_price_paise"}, "unit_cost_paise": ln["unit_price_paise"]}
        for ln in lines
    ]
    return {"supplier_id": supplier["id"], "location_id": shop["id"], "lines": lines, **extra}


async def _buy(client: Any, body: dict[str, Any], *, expect: int = 201) -> Any:
    r = await client.post("/api/w/purchases", json=body, headers=idem())
    assert r.status_code == expect, f"buy -> {r.status_code} {r.text}"
    return r.json()


async def test_purchase_adds_stock_and_records_what_we_owe_the_supplier(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg, supplier = await _setup(admin_client, client_factory)
    body = _purchase(
        shop,
        supplier,
        [factory.line(banana, kg, 500_000, 30)],
        supplier_bill_no="TF-118",
        payments=[{"method": "cash", "amount_paise": 500_000}],
    )
    p = await _buy(a, body)
    assert (
        p["purchase_number"].endswith("/P/000001") and p["status"] == "active" and p["supplier_name"] == "Theni Farms"
    )
    assert p["total_paise"] == 1_500_000 and p["paid_paise"] == 500_000 and p["credit_paise"] == 1_000_000
    assert p["lines"][0]["amount_paise"] == 1_500_000 and p["lines"][0]["description"] == "Banana"
    assert await factory.stock_of(a, banana, shop) == 500_000
    # Rs 15,000 bought, Rs 5,000 paid: we owe Rs 10,000 (negative = we owe them)
    assert await factory.party_balance(a, "suppliers", supplier["id"]) == -1_000_000
    assert (await a.get(f"/api/w/purchases/{p['id']}")).json()["purchase_number"] == p["purchase_number"]
    assert [x["id"] for x in (await a.get("/api/w/purchases", params={"q": "TF-118"})).json()] == [p["id"]]


async def test_void_purchase_reverses_stock_and_account_but_not_after_the_goods_were_sold(
    admin_client: Any, client_factory: Any
) -> None:
    a, _, shop, banana, kg, supplier = await _setup(admin_client, client_factory)
    first = await _buy(
        a,
        _purchase(
            shop, supplier, [factory.line(banana, kg, 10_000, 30)], payments=[{"method": "upi", "amount_paise": 10_000}]
        ),
    )
    r = await a.post(f"/api/w/purchases/{first['id']}/void", json={"reason": "wrong supplier"}, headers=idem())
    assert r.status_code == 200 and r.json()["status"] == "void"
    assert await factory.stock_of(a, banana, shop) == 0
    assert await factory.party_balance(a, "suppliers", supplier["id"]) == 0
    assert sorted(p["direction"] for p in r.json()["payments"]) == ["in", "out"]
    again = await a.post(f"/api/w/purchases/{first['id']}/void", json={"reason": "again"}, headers=idem())
    assert again.status_code == 409 and again.json()["code"] == "already_void"

    second = await _buy(a, _purchase(shop, supplier, [factory.line(banana, kg, 10_000, 30)]))
    await factory.sell(
        a, shop, [factory.line(banana, kg, 8_000, 45)], payments=[{"method": "cash", "amount_paise": 36_000}]
    )
    r = await a.post(f"/api/w/purchases/{second['id']}/void", json={"reason": "changed my mind"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "insufficient_stock"
    assert (await a.get(f"/api/w/purchases/{second['id']}")).json()["status"] == "active"  # nothing half-undone
    assert await factory.party_balance(a, "suppliers", supplier["id"]) == -30_000


async def test_purchase_validation(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg, supplier = await _setup(admin_client, client_factory)
    customer = await factory.customer(a, "Not a supplier")
    lines = [factory.line(banana, kg, 1_000, 30)]
    tomorrow = (today_ist() + timedelta(days=1)).isoformat()
    assert (await _buy(a, _purchase(shop, supplier, lines, purchase_date=tomorrow), expect=422))[
        "code"
    ] == "future_date"
    assert (
        await _buy(
            a, _purchase(shop, supplier, lines, payments=[{"method": "cash", "amount_paise": 99_999}]), expect=422
        )
    )["code"] == "overpaid"
    assert (await _buy(a, _purchase(shop, supplier, [factory.line(banana, kg, 1_000, 0)]), expect=422))[
        "code"
    ] == "zero_total"
    assert (await _buy(a, _purchase(shop, customer, lines), expect=404))[
        "code"
    ] == "not_found"  # customers are not suppliers
    old = (today_ist() - timedelta(days=3)).isoformat()
    assert (await _buy(a, _purchase(shop, supplier, lines, purchase_date=old)))["purchase_date"] == old
    assert await factory.stock_of(a, banana, shop) == 1_000


async def test_purchases_are_isolated_and_role_checked(admin_client: Any, client_factory: Any) -> None:
    a, business_a, shop_a, banana_a, kg_a, supplier_a = await _setup(admin_client, client_factory)
    b, _, shop_b, banana_b, kg_b, supplier_b = await _setup(admin_client, client_factory)
    p = await _buy(a, _purchase(shop_a, supplier_a, [factory.line(banana_a, kg_a, 1_000, 30)]))
    assert (await b.get(f"/api/w/purchases/{p['id']}")).status_code == 404
    assert (
        await b.post(f"/api/w/purchases/{p['id']}/void", json={"reason": "not mine"}, headers=idem())
    ).status_code == 404
    assert (await b.get("/api/w/purchases")).json() == []
    await _buy(b, _purchase(shop_b, supplier_a, [factory.line(banana_b, kg_b, 1_000, 30)]), expect=404)
    await _buy(b, _purchase(shop_a, supplier_b, [factory.line(banana_b, kg_b, 1_000, 30)]), expect=404)

    stock_staff, _ = await make_business(admin_client, client_factory, role="stock", business_id=business_a)
    billing, _ = await make_business(admin_client, client_factory, role="billing", business_id=business_a)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_a)
    body = _purchase(shop_a, supplier_a, [factory.line(banana_a, kg_a, 1_000, 30)])
    assert (await _buy(stock_staff, body))["status"] == "active"  # godown staff receive goods
    assert (await _buy(billing, body, expect=403))["code"] == "permission_denied"
    assert (await _buy(viewer, body, expect=403))["code"] == "permission_denied"
    assert len((await viewer.get("/api/w/purchases")).json()) == 2
    r = await stock_staff.post(f"/api/w/purchases/{p['id']}/void", json={"reason": "not allowed"}, headers=idem())
    assert r.status_code == 403  # only managers and owners cancel


async def test_customer_payment_lowers_what_they_owe_and_can_be_reversed(
    admin_client: Any, client_factory: Any
) -> None:
    a, _, *_ = await _setup(admin_client, client_factory)
    c = await factory.customer(a, "Anand Hotel", opening_balance_paise=70_000)
    pay = await factory.post(
        a,
        "/api/w/money/payments",
        {"party_id": c["id"], "direction": "in", "method": "upi", "amount_paise": 30_000, "note": "part payment"},
    )
    assert pay["direction"] == "in" and pay["method"] == "upi"
    assert await factory.party_balance(a, "customers", c["id"]) == 40_000
    rev = await factory.post(a, f"/api/w/money/payments/{pay['id']}/reverse", {"reason": "bounced"})
    assert rev["direction"] == "out" and rev["reversal_of"] == pay["id"]
    assert await factory.party_balance(a, "customers", c["id"]) == 70_000
    again = await a.post(f"/api/w/money/payments/{pay['id']}/reverse", json={"reason": "twice"}, headers=idem())
    assert again.status_code == 409 and again.json()["code"] == "already_reversed"
    r = await a.post(f"/api/w/money/payments/{rev['id']}/reverse", json={"reason": "undo undo"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "not_reversible"
    listed = (await a.get("/api/w/money/payments", params={"party_id": c["id"]})).json()
    assert [p["id"] for p in listed] == [rev["id"], pay["id"]]


async def test_paying_a_supplier_and_payments_that_belong_to_a_bill(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, banana, kg, supplier = await _setup(admin_client, client_factory)
    await _buy(a, _purchase(shop, supplier, [factory.line(banana, kg, 10_000, 30)]))  # we owe Rs 300
    await factory.post(
        a,
        "/api/w/money/payments",
        {"party_id": supplier["id"], "direction": "out", "method": "bank", "amount_paise": 20_000},
    )
    assert await factory.party_balance(a, "suppliers", supplier["id"]) == -10_000
    bill = await factory.sell(
        a, shop, [factory.line(banana, kg, 1_000, 45)], payments=[{"method": "cash", "amount_paise": 4_500}]
    )
    bill_payment = bill["payments"][0]
    r = await a.post(f"/api/w/money/payments/{bill_payment['id']}/reverse", json={"reason": "fix"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "payment_belongs_to_document"


async def test_money_is_isolated_role_checked_and_module_gated(admin_client: Any, client_factory: Any) -> None:
    a, business_a, *_ = await _setup(admin_client, client_factory)
    b, *_ = await _setup(admin_client, client_factory)
    c = await factory.customer(a, "A customer", opening_balance_paise=10_000)
    body = {"party_id": c["id"], "direction": "in", "method": "cash", "amount_paise": 1_000}
    r = await b.post("/api/w/money/payments", json=body, headers=idem())
    assert r.status_code == 404  # B cannot post into A's customer account
    p = await factory.post(a, "/api/w/money/payments", body)
    assert (
        await b.post(f"/api/w/money/payments/{p['id']}/reverse", json={"reason": "not mine"}, headers=idem())
    ).status_code == 404
    assert (await b.get("/api/w/money/payments")).json() == []

    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_a)
    stock_staff, _ = await make_business(admin_client, client_factory, role="stock", business_id=business_a)
    assert len((await viewer.get("/api/w/money/payments")).json()) == 1
    assert (await viewer.post("/api/w/money/payments", json=body, headers=idem())).status_code == 403
    assert (await stock_staff.get("/api/w/money/payments")).status_code == 403
    no_money, _ = await make_business(admin_client, client_factory, modules=["customers"])
    assert (await no_money.get("/api/w/money/payments")).json()["code"] == "module_disabled"
    assert await factory.party_balance(a, "customers", c["id"]) == 9_000
