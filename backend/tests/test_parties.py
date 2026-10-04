"""Customers, suppliers, the party ledger and the crate ledger."""

import uuid
from typing import Any

import psycopg
import pytest

from tests import factory
from tests.conftest import app_conn, idem, make_business, random_phone, superuser_conn


async def test_customer_with_opening_balance_writes_a_ledger_entry(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    c = await factory.customer(
        a, "Ravi", phone=random_phone(), opening_balance_paise=250_000, credit_limit_paise=1_000_000
    )
    assert c["balance_paise"] == 250_000 and c["credit_limit_paise"] == 1_000_000 and c["kind"] == "customer"
    ledger = (await a.get(f"/api/w/customers/{c['id']}/ledger")).json()
    assert [(e["entry_type"], e["amount_paise"]) for e in ledger] == [("opening", 250_000)]
    assert (await a.get(f"/api/w/customers/{c['id']}")).json()["balance_paise"] == 250_000


async def test_supplier_endpoints_do_not_serve_customers(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    c = await factory.customer(a)
    s = await factory.supplier(a, opening_balance_paise=-90_000)
    assert s["balance_paise"] == -90_000
    assert (await a.get(f"/api/w/suppliers/{c['id']}")).status_code == 404
    assert (await a.get(f"/api/w/customers/{s['id']}")).status_code == 404
    assert [x["id"] for x in (await a.get("/api/w/customers")).json()] == [c["id"]]


async def test_phone_validation_and_uniqueness_per_kind(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    phone = random_phone()
    await factory.customer(a, "One", phone=phone)
    r = await a.post("/api/w/customers", json={"name": "Two", "phone": phone}, headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "party_phone_taken"
    await factory.supplier(a, "Same phone, different kind", phone=phone)  # allowed: another kind
    r = await a.post("/api/w/customers", json={"name": "Bad", "phone": "123"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "invalid_phone"
    r = await a.post("/api/w/customers", json={"name": "Bad GST", "gstin": "nope"}, headers=idem())
    assert r.status_code == 422


async def test_update_and_search(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    c = await factory.customer(a, "Kumar", name_ta="குமார்", phone=random_phone())
    r = await a.patch(f"/api/w/customers/{c['id']}", json={"phone": None, "address": "Koyambedu"}, headers=idem())
    assert r.status_code == 200 and r.json()["phone"] is None and r.json()["address"] == "Koyambedu"
    assert len((await a.get("/api/w/customers", params={"q": "kum"})).json()) == 1
    assert (await a.get("/api/w/customers", params={"q": "zzz"})).json() == []
    await a.patch(f"/api/w/customers/{c['id']}", json={"is_active": False}, headers=idem())
    assert (await a.get("/api/w/customers")).json() == []


async def test_balance_adjustment_needs_a_reason_and_is_appended(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    c = await factory.customer(a, opening_balance_paise=100_000)
    url = f"/api/w/customers/{c['id']}/adjustments"
    r = await a.post(url, json={"amount_paise": -30_000, "note": "x"}, headers=idem())
    assert r.status_code == 422  # reason too short
    r = await a.post(url, json={"amount_paise": 0, "note": "no change"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "zero_adjustment"
    await factory.post(a, url, {"amount_paise": -30_000, "note": "discount given"})
    assert (await a.get(f"/api/w/customers/{c['id']}")).json()["balance_paise"] == 70_000
    ledger = (await a.get(f"/api/w/customers/{c['id']}/ledger")).json()
    assert [e["entry_type"] for e in ledger] == ["adjustment", "opening"]  # newest first


async def test_crate_ledger_tracks_crates_held(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    c = await factory.customer(a)
    loc = await factory.location(a)
    issue = {"party_id": c["id"], "direction": "issued", "quantity": 10, "location_id": loc["id"]}
    await factory.post(a, "/api/w/crates/entries", issue)
    await factory.post(a, "/api/w/crates/entries", {"party_id": c["id"], "direction": "returned", "quantity": 4})
    assert (await a.get(f"/api/w/customers/{c['id']}")).json()["crates_held"] == 6
    assert (await a.get("/api/w/crates/balances")).json() == [{"party_id": c["id"], "crates_held": 6}]
    await factory.post(
        a, f"/api/w/customers/{c['id']}/crate-adjustments", {"quantity": -6, "note": "lost crates written off"}
    )
    assert (await a.get("/api/w/crates/balances")).json() == []  # nothing outstanding
    assert len((await a.get(f"/api/w/customers/{c['id']}/crates")).json()) == 3


async def test_crate_entry_rejects_foreign_party_and_location(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    party_a = await factory.customer(a)
    loc_a = await factory.location(a, "A shop")
    party_b = await factory.customer(b)
    body = {"party_id": party_a["id"], "direction": "issued", "quantity": 1}
    assert (await b.post("/api/w/crates/entries", json=body, headers=idem())).status_code == 404
    body = {"party_id": party_b["id"], "direction": "issued", "quantity": 1, "location_id": loc_a["id"]}
    assert (await b.post("/api/w/crates/entries", json=body, headers=idem())).status_code == 404


async def test_parties_isolated_between_businesses(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    c = await factory.customer(a, "Secret customer", opening_balance_paise=5_000)
    pid = c["id"]
    assert (await b.get(f"/api/w/customers/{pid}")).status_code == 404
    assert (await b.patch(f"/api/w/customers/{pid}", json={"name": "x"}, headers=idem())).status_code == 404
    assert (await b.get(f"/api/w/customers/{pid}/ledger")).status_code == 404
    r = await b.post(f"/api/w/customers/{pid}/adjustments", json={"amount_paise": 1, "note": "sneaky"}, headers=idem())
    assert r.status_code == 404
    assert (await b.get(f"/api/w/customers/{pid}/crates")).status_code == 404
    assert (await b.get("/api/w/customers")).json() == []
    assert (await a.get(f"/api/w/customers/{pid}")).json()["balance_paise"] == 5_000  # untouched


async def test_ledgers_are_append_only_and_tenant_checked_by_the_database(
    admin_client: Any, client_factory: Any
) -> None:
    a, business_a = await make_business(admin_client, client_factory)
    _, business_b = await make_business(admin_client, client_factory)
    c = await factory.customer(a, opening_balance_paise=1_000)
    await factory.post(a, "/api/w/crates/entries", {"party_id": c["id"], "direction": "issued", "quantity": 2})

    with app_conn() as conn:
        for stmt in (
            "UPDATE party_ledger_entries SET amount_paise = 1",
            "DELETE FROM party_ledger_entries",
            "UPDATE crate_ledger_entries SET quantity = 1",
            "DELETE FROM crate_ledger_entries",
        ):
            conn.execute("SELECT set_config('app.business_id', %s, true)", (business_a,))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(stmt)  # type: ignore[arg-type]
            conn.rollback()
    with superuser_conn() as conn:  # even a superuser hits the trigger
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("UPDATE party_ledger_entries SET amount_paise = 1")
        # composite FK: an entry for business B cannot point at business A's party
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "INSERT INTO party_ledger_entries (id, business_id, party_id, entry_type, amount_paise, created_by) "
                "SELECT %s, %s, %s, 'adjustment', 5, id FROM users LIMIT 1",
                (uuid.uuid4(), business_b, c["id"]),
            )


async def test_roles_and_module_gates(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    billing, _ = await make_business(admin_client, client_factory, role="billing", business_id=business_id)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    c = await factory.customer(billing, "Made by counter staff")  # billing may manage parties
    assert (await viewer.get(f"/api/w/customers/{c['id']}")).status_code == 200
    r = await viewer.post("/api/w/customers", json={"name": "No"}, headers=idem())
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    only_customers, _ = await make_business(admin_client, client_factory, modules=["customers"])
    assert (await only_customers.get("/api/w/customers")).status_code == 200
    assert (await only_customers.get("/api/w/suppliers")).json()["code"] == "module_disabled"
    assert (await only_customers.get("/api/w/crates/balances")).status_code == 403  # crates need the stock module
    assert (await owner.get("/api/w/customers")).status_code == 200
