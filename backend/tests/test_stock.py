"""Stock: opening, adjustments, transfers, wastage, reversals, balances and access rules."""

import asyncio
from typing import Any

import psycopg
import pytest

from tests import factory
from tests.conftest import app_conn, idem, make_business, superuser_conn

Setup = tuple[Any, str, dict[str, Any], dict[str, Any], dict[str, Any]]


async def _setup(admin_client: Any, client_factory: Any) -> Setup:
    a, business_id = await make_business(admin_client, client_factory)
    shop = await factory.location(a, "Shop")
    godown = await factory.location(a, "Godown")
    banana = await factory.product(a, "Banana")
    return a, business_id, shop, godown, banana


def _line(product: dict[str, Any], quantity: int) -> dict[str, Any]:
    return {"product_id": product["id"], "quantity": quantity}


def _transfer(src: dict[str, Any], dst: dict[str, Any], *lines: dict[str, Any]) -> dict[str, Any]:
    return {"from_location_id": src["id"], "to_location_id": dst["id"], "lines": list(lines)}


async def test_opening_stock_shows_in_balances(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, banana = await _setup(admin_client, client_factory)
    v = await factory.post(a, f"/api/w/products/{banana['id']}/varieties", {"name": "Robusta"})
    g = await factory.grade(a, "A")
    m = await factory.opening(
        a, shop["id"], banana["id"], 50_000, variety_id=v["id"], grade_id=g["id"], note="stock take"
    )
    assert m["quantity"] == 50_000 and m["movement_type"] == "opening"
    rows = await factory.balances(a)
    assert len(rows) == 1
    assert rows[0]["quantity"] == 50_000 and rows[0]["product_name"] == "Banana"
    assert rows[0]["variety_name"] == "Robusta" and rows[0]["grade_name"] == "A" and rows[0]["kind"] == "weight"


async def test_variety_of_another_product_is_rejected(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, banana = await _setup(admin_client, client_factory)
    tomato = await factory.product(a, "Tomato")
    v = await factory.post(a, f"/api/w/products/{tomato['id']}/varieties", {"name": "Hybrid"})
    body = {"location_id": shop["id"], "product_id": banana["id"], "variety_id": v["id"], "quantity": 1}
    r = await a.post("/api/w/stock/opening", json=body, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "variety_mismatch"


async def test_adjustment_cannot_take_stock_below_zero(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, banana = await _setup(admin_client, client_factory)
    await factory.opening(a, shop["id"], banana["id"], 10_000)
    body = {"location_id": shop["id"], "product_id": banana["id"], "quantity": -10_001, "reason": "count correction"}
    r = await a.post("/api/w/stock/adjustments", json=body, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "insufficient_stock"
    await factory.post(a, "/api/w/stock/adjustments", {**body, "quantity": -4_000})
    assert (await factory.balances(a))[0]["quantity"] == 6_000
    r = await a.post("/api/w/stock/adjustments", json={**body, "quantity": 0}, headers=idem())
    assert r.status_code == 422
    r = await a.post("/api/w/stock/adjustments", json={**body, "quantity": 5, "reason": "x"}, headers=idem())
    assert r.status_code == 422  # a real reason is mandatory


async def test_transfer_moves_stock_and_is_all_or_nothing(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, godown, banana = await _setup(admin_client, client_factory)
    tomato = await factory.product(a, "Tomato")
    await factory.opening(a, godown["id"], banana["id"], 30_000)
    await factory.opening(a, godown["id"], tomato["id"], 5_000)
    t = await factory.post(
        a, "/api/w/stock/transfers", _transfer(godown, shop, _line(banana, 12_000), _line(tomato, 5_000))
    )
    assert len(t["movements"]) == 4
    by_loc = {(r["location_id"], r["product_name"]): r["quantity"] for r in await factory.balances(a)}
    assert by_loc == {(godown["id"], "Banana"): 18_000, (shop["id"], "Banana"): 12_000, (shop["id"], "Tomato"): 5_000}
    assert len((await a.get("/api/w/stock/transfers")).json()) == 1

    # second line is short: nothing at all may move
    bad = _transfer(godown, shop, _line(banana, 1_000), _line(tomato, 1))
    r = await a.post("/api/w/stock/transfers", json=bad, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "insufficient_stock"
    assert {(r["location_id"], r["product_name"]): r["quantity"] for r in await factory.balances(a)} == by_loc
    assert len((await a.get("/api/w/stock/transfers")).json()) == 1

    same = _transfer(shop, shop, _line(banana, 1))
    assert (await a.post("/api/w/stock/transfers", json=same, headers=idem())).status_code == 422


async def test_wastage_reduces_stock_and_reversal_restores_it(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, banana = await _setup(admin_client, client_factory)
    await factory.opening(a, shop["id"], banana["id"], 20_000)
    wastage = {"location_id": shop["id"], "product_id": banana["id"], "quantity": 3_000, "reason_code": "rotten"}
    w = await factory.post(a, "/api/w/stock/wastage", wastage)
    assert w["reversed"] is False and (await factory.balances(a))[0]["quantity"] == 17_000
    rev = await factory.post(a, f"/api/w/stock/movements/{w['movement_id']}/reverse", {"reason": "entered by mistake"})
    assert rev["movement_type"] == "reversal" and rev["quantity"] == 3_000 and rev["reversal_of"] == w["movement_id"]
    assert (await factory.balances(a))[0]["quantity"] == 20_000
    assert (await a.get("/api/w/stock/wastage")).json()[0]["reversed"] is True
    url = f"/api/w/stock/movements/{w['movement_id']}/reverse"
    again = await a.post(url, json={"reason": "twice?"}, headers=idem())
    assert again.status_code == 409 and again.json()["code"] == "already_reversed"


async def test_reversal_is_refused_when_stock_has_moved_on(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, godown, banana = await _setup(admin_client, client_factory)
    m = await factory.opening(a, shop["id"], banana["id"], 5_000)
    await factory.post(a, "/api/w/stock/transfers", _transfer(shop, godown, _line(banana, 4_000)))
    r = await a.post(f"/api/w/stock/movements/{m['id']}/reverse", json={"reason": "wrong entry"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "insufficient_stock"
    moves = (await a.get("/api/w/stock/movements")).json()
    transfer_out = next(x for x in moves if x["movement_type"] == "transfer_out")
    r = await a.post(f"/api/w/stock/movements/{transfer_out['id']}/reverse", json={"reason": "undo it"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "not_reversible"


async def test_concurrent_stock_outs_cannot_oversell(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, banana = await _setup(admin_client, client_factory)
    await factory.opening(a, shop["id"], banana["id"], 100)
    body = {"location_id": shop["id"], "product_id": banana["id"], "quantity": 60, "reason_code": "damaged"}
    results = await asyncio.gather(*(a.post("/api/w/stock/wastage", json=body, headers=idem()) for _ in range(4)))
    assert sorted(r.status_code for r in results) == [201, 422, 422, 422]
    assert (await factory.balances(a))[0]["quantity"] == 40


async def test_idempotent_stock_write_creates_one_movement(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, _, banana = await _setup(admin_client, client_factory)
    headers = idem()
    body = {"location_id": shop["id"], "product_id": banana["id"], "quantity": 700}
    first = await a.post("/api/w/stock/opening", json=body, headers=headers)
    again = await a.post("/api/w/stock/opening", json=body, headers=headers)
    assert first.status_code == again.status_code == 201 and first.json() == again.json()
    assert (await factory.balances(a))[0]["quantity"] == 700


async def test_movements_list_paginates_and_filters(admin_client: Any, client_factory: Any) -> None:
    a, _, shop, godown, banana = await _setup(admin_client, client_factory)
    for qty in (1, 2, 3):
        await factory.opening(a, shop["id"], banana["id"], qty)
    await factory.opening(a, godown["id"], banana["id"], 9)
    first = (await a.get("/api/w/stock/movements", params={"limit": 2})).json()
    assert [m["quantity"] for m in first] == [9, 3]
    rest = (await a.get("/api/w/stock/movements", params={"limit": 5, "before_id": first[-1]["id"]})).json()
    assert [m["quantity"] for m in rest] == [2, 1]
    only_shop = (await a.get("/api/w/stock/movements", params={"location_id": shop["id"]})).json()
    assert len(only_shop) == 3


async def test_restricted_staff_only_touch_their_locations(admin_client: Any, client_factory: Any) -> None:
    owner, business_id, shop, godown, banana = await _setup(admin_client, client_factory)
    await factory.opening(owner, shop["id"], banana["id"], 1_000)
    await factory.opening(owner, godown["id"], banana["id"], 2_000)
    staff, _ = await make_business(
        admin_client, client_factory, role="stock", business_id=business_id, location_ids=[shop["id"]]
    )
    assert [r["location_id"] for r in await factory.balances(staff)] == [shop["id"]]
    assert {m["location_id"] for m in (await staff.get("/api/w/stock/movements")).json()} == {shop["id"]}
    body = {"location_id": godown["id"], "product_id": banana["id"], "quantity": 5}
    assert (await staff.post("/api/w/stock/opening", json=body, headers=idem())).status_code == 404
    move = _transfer(shop, godown, _line(banana, 1))
    assert (await staff.post("/api/w/stock/transfers", json=move, headers=idem())).status_code == 404
    ok = {"location_id": shop["id"], "product_id": banana["id"], "quantity": 5}
    assert (await staff.post("/api/w/stock/opening", json=ok, headers=idem())).status_code == 201


async def test_roles_gate_stock_writes(admin_client: Any, client_factory: Any) -> None:
    _, business_id, shop, _, banana = await _setup(admin_client, client_factory)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    billing, _ = await make_business(admin_client, client_factory, role="billing", business_id=business_id)
    body = {"location_id": shop["id"], "product_id": banana["id"], "quantity": 5}
    for c in (viewer, billing):
        r = await c.post("/api/w/stock/opening", json=body, headers=idem())
        assert r.status_code == 403 and r.json()["code"] == "permission_denied"
        assert (await c.get("/api/w/stock/balances")).status_code == 200
    no_stock, _ = await make_business(admin_client, client_factory, modules=["sell"])
    assert (await no_stock.get("/api/w/stock/balances")).json()["code"] == "module_disabled"


async def test_stock_isolated_between_businesses(admin_client: Any, client_factory: Any) -> None:
    a, _, shop_a, _, banana_a = await _setup(admin_client, client_factory)
    b, _, shop_b, _, banana_b = await _setup(admin_client, client_factory)
    m = await factory.opening(a, shop_a["id"], banana_a["id"], 999)
    assert (await factory.balances(b)) == []
    assert (await b.get("/api/w/stock/movements")).json() == []
    # B cannot use A's location or product, or reverse A's movement
    for body in (
        {"location_id": shop_a["id"], "product_id": banana_b["id"], "quantity": 1},
        {"location_id": shop_b["id"], "product_id": banana_a["id"], "quantity": 1},
    ):
        assert (await b.post("/api/w/stock/opening", json=body, headers=idem())).status_code == 404
    r = await b.post(f"/api/w/stock/movements/{m['id']}/reverse", json={"reason": "not mine"}, headers=idem())
    assert r.status_code == 404
    move = _transfer(shop_a, shop_b, _line(banana_b, 1))
    assert (await b.post("/api/w/stock/transfers", json=move, headers=idem())).status_code == 404
    assert (await factory.balances(a))[0]["quantity"] == 999


async def test_stock_tables_are_append_only(admin_client: Any, client_factory: Any) -> None:
    a, business_a, shop, godown, banana = await _setup(admin_client, client_factory)
    await factory.opening(a, shop["id"], banana["id"], 100)
    wastage = {"location_id": shop["id"], "product_id": banana["id"], "quantity": 10, "reason_code": "other"}
    await factory.post(a, "/api/w/stock/wastage", wastage)
    await factory.post(a, "/api/w/stock/transfers", _transfer(shop, godown, _line(banana, 5)))
    with app_conn() as conn:
        for table in ("stock_movements", "wastage_entries", "stock_transfers"):
            conn.execute("SELECT set_config('app.business_id', %s, true)", (business_a,))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"DELETE FROM {table}")  # type: ignore[arg-type]
            conn.rollback()
    with superuser_conn() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("UPDATE stock_movements SET quantity = 1")
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("TRUNCATE stock_movements, wastage_entries")
