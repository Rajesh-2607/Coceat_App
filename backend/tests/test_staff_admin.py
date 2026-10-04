"""Staff management (workspace and platform admin), audit filters, business updates and the Home summary."""

import uuid
from typing import Any

from tests import factory
from tests.conftest import TEST_PASSWORD, idem, make_business, random_phone, username_for


def _staff_body(role: str = "viewer", **extra: Any) -> dict[str, Any]:
    phone = random_phone()
    return {
        "phone": phone,
        "name": "New Staff",
        "role": role,
        "username": username_for(phone),
        "password": TEST_PASSWORD,
        **extra,
    }


async def test_owner_adds_lists_and_updates_staff(admin_client: Any, client_factory: Any) -> None:
    owner, _ = await make_business(admin_client, client_factory)
    shop = await factory.location(owner, "Shop")
    staff = await factory.post(owner, "/api/w/staff", _staff_body("billing", location_ids=[shop["id"]]))
    assert staff["role"] == "billing" and staff["location_ids"] == [shop["id"]] and staff["is_active"] is True
    listed = (await owner.get("/api/w/staff")).json()
    assert {s["role"] for s in listed} == {"owner", "billing"}

    r = await owner.patch(
        f"/api/w/staff/{staff['membership_id']}", json={"role": "stock", "location_ids": None}, headers=idem()
    )
    assert r.status_code == 200 and r.json()["role"] == "stock" and r.json()["location_ids"] is None
    r = await owner.patch(f"/api/w/staff/{staff['membership_id']}", json={"is_active": False}, headers=idem())
    assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["role"] == "stock"


async def test_deactivated_staff_cannot_use_the_workspace(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    member, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    assert (await member.get("/api/w/locations")).status_code == 200
    staff = (await owner.get("/api/w/staff")).json()
    victim = next(s for s in staff if s["role"] == "viewer")
    await owner.patch(f"/api/w/staff/{victim['membership_id']}", json={"is_active": False}, headers=idem())
    assert (await member.get("/api/w/locations")).status_code == 401


async def test_only_owner_manages_staff_and_manager_may_view(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    manager, _ = await make_business(admin_client, client_factory, role="manager", business_id=business_id)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    assert (await manager.get("/api/w/staff")).status_code == 200
    r = await manager.post("/api/w/staff", json=_staff_body(), headers=idem())
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert (await viewer.get("/api/w/staff")).status_code == 403


async def test_owner_cannot_change_own_access_and_last_owner_is_protected(
    admin_client: Any, client_factory: Any
) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    me = next(s for s in (await owner.get("/api/w/staff")).json() if s["role"] == "owner")
    r = await owner.patch(f"/api/w/staff/{me['membership_id']}", json={"role": "viewer"}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "cannot_edit_self"
    # the platform team cannot strand a business without an owner either
    r = await admin_client.patch(
        f"/api/admin/businesses/{business_id}/members/{me['membership_id']}", json={"is_active": False}
    )
    assert r.status_code == 422 and r.json()["code"] == "last_owner"
    r = await admin_client.patch(
        f"/api/admin/businesses/{business_id}/members/{me['membership_id']}", json={"role": "manager"}
    )
    assert r.status_code == 422 and r.json()["code"] == "last_owner"
    # with a second owner it is allowed
    second = await factory.post(owner, "/api/w/staff", _staff_body("owner"))
    assert second["role"] == "owner"
    r = await admin_client.patch(
        f"/api/admin/businesses/{business_id}/members/{me['membership_id']}", json={"role": "manager"}
    )
    assert r.status_code == 200 and r.json()["role"] == "manager"


async def test_staff_locations_must_belong_to_the_business(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    foreign = await factory.location(b, "B only")
    r = await a.post("/api/w/staff", json=_staff_body(location_ids=[foreign["id"]]), headers=idem())
    assert r.status_code == 404
    r = await a.post("/api/w/staff", json=_staff_body(location_ids=[str(uuid.uuid4())]), headers=idem())
    assert r.status_code == 404


async def test_staff_isolated_between_businesses(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    staff_a = await factory.post(a, "/api/w/staff", _staff_body("viewer"))
    assert staff_a["membership_id"] not in {s["membership_id"] for s in (await b.get("/api/w/staff")).json()}
    r = await b.patch(f"/api/w/staff/{staff_a['membership_id']}", json={"role": "owner"}, headers=idem())
    assert r.status_code == 404
    assert (await a.get("/api/w/staff")).json()[-1]["role"] == "viewer"


async def test_audit_log_filters_and_actor_names(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    shop = await factory.location(a, "Shop")
    p = await factory.product(a, "Banana")
    await factory.opening(a, shop["id"], p["id"], 100)
    everything = (await a.get("/api/w/audit-events")).json()["items"]
    assert any(e["actor_name"] for e in everything)
    stock = (await a.get("/api/w/audit-events", params={"action": "stock"})).json()["items"]
    assert [e["action"] for e in stock] == ["stock.opening"]
    exact = (await a.get("/api/w/audit-events", params={"action": "location.create"})).json()["items"]
    assert len(exact) == 1
    by_entity = (await a.get("/api/w/audit-events", params={"entity_type": "product"})).json()["items"]
    assert [e["action"] for e in by_entity] == ["product.create"]
    actor = next(e["actor_user_id"] for e in everything if e["actor_user_id"])
    assert (await a.get("/api/w/audit-events", params={"actor_user_id": actor})).json()["items"]
    assert (await a.get("/api/w/audit-events", params={"actor_user_id": str(uuid.uuid4())})).json()["items"] == []
    future = (await a.get("/api/w/audit-events", params={"date_from": "2999-01-01T00:00:00Z"})).json()["items"]
    assert future == []


async def test_admin_updates_business_and_lists_verticals_and_members(admin_client: Any, client_factory: Any) -> None:
    verticals = (await admin_client.get("/api/admin/verticals")).json()
    assert {"banana", "vegetable", "flower", "tomato"} <= {v["key"] for v in verticals}
    owner, business_id = await make_business(admin_client, client_factory)
    r = await admin_client.patch(
        f"/api/admin/businesses/{business_id}",
        json={"name": "Renamed", "gstin": "33ABCDE1234F1Z5", "enabled_modules": ["sell", "stock", "audit"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert (
        body["name"] == "Renamed"
        and body["gstin"] == "33ABCDE1234F1Z5"
        and body["enabled_modules"] == ["audit", "sell", "stock"]
    )
    assert (await owner.get("/api/w/customers")).json()["code"] == "module_disabled"  # takes effect immediately
    r = await admin_client.patch(f"/api/admin/businesses/{business_id}", json={"gstin": None})
    assert r.json()["gstin"] is None and r.json()["name"] == "Renamed"
    r = await admin_client.patch(f"/api/admin/businesses/{business_id}", json={"gstin": "bad"})
    assert r.status_code == 422
    assert (await admin_client.get(f"/api/admin/businesses/{business_id}")).json()["name"] == "Renamed"
    members = (await admin_client.get(f"/api/admin/businesses/{business_id}/members")).json()
    assert [m["role"] for m in members] == ["owner"]
    events = (await owner.get("/api/w/audit-events")).json()["items"]
    updates = [e for e in events if e["action"] == "business.update"]
    assert any(e["before"]["name"] != e["after"]["name"] for e in updates)  # before/after are recorded
    r = await admin_client.patch(f"/api/admin/businesses/{business_id}", json={"status": "suspended"})
    assert r.json()["status"] == "suspended"
    assert (await owner.get("/api/w/staff")).status_code == 401


async def test_business_admin_endpoints_need_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    assert (await owner.patch(f"/api/admin/businesses/{business_id}", json={"name": "x"})).status_code == 403
    assert (await owner.get("/api/admin/verticals")).status_code == 403
    assert (await owner.get(f"/api/admin/businesses/{business_id}/members")).status_code == 403
    missing = uuid.uuid4()
    assert (await admin_client.get(f"/api/admin/businesses/{missing}")).status_code == 404
    assert (await admin_client.patch(f"/api/admin/businesses/{missing}", json={"name": "x"})).status_code == 404


async def test_new_business_gets_default_units_only_for_itself(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    ids_a = {u["id"] for u in (await a.get("/api/w/units")).json()}
    ids_b = {u["id"] for u in (await b.get("/api/w/units")).json()}
    assert ids_a and ids_b and ids_a.isdisjoint(ids_b)


async def test_home_summary(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    shop = await factory.location(a, "Shop")
    p = await factory.product(a, "Banana")
    await factory.opening(a, shop["id"], p["id"], 10_000)
    debtor = await factory.customer(a, "Big debtor", opening_balance_paise=80_000)
    await factory.customer(a, "Small debtor", opening_balance_paise=20_000)
    await factory.supplier(a, "We owe", opening_balance_paise=-45_000)
    await factory.post(a, "/api/w/crates/entries", {"party_id": debtor["id"], "direction": "issued", "quantity": 7})
    home = (await a.get("/api/w/home")).json()
    assert home["locations"] == 1 and home["products"] == 1 and home["customers"] == 2 and home["suppliers"] == 1
    assert home["stock_items"] == 1 and home["negative_stock_items"] == 0
    assert home["receivable_paise"] == 100_000 and home["payable_paise"] == 45_000
    assert home["crates_outstanding"] == 7
    assert [d["name"] for d in home["top_owing_customers"]] == ["Big debtor", "Small debtor"]


async def test_home_hides_parts_the_business_does_not_have(admin_client: Any, client_factory: Any) -> None:
    only_sell, _ = await make_business(admin_client, client_factory, modules=["sell"])
    home = (await only_sell.get("/api/w/home")).json()
    assert all(
        home[k] is None for k in ("locations", "products", "customers", "suppliers", "stock_items", "receivable_paise")
    )
    assert home["top_owing_customers"] == []


async def test_home_shows_todays_sales(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    shop = await factory.location(a, "Shop")
    p = await factory.product(a, "Banana")
    kg = await factory.unit(a, "kg")
    await factory.opening(a, shop["id"], p["id"], 100_000)
    assert (await a.get("/api/w/home")).json()["today_sales_paise"] == 0
    await factory.sell(a, shop, [factory.line(p, kg, 2_000, 45)], payments=[{"method": "cash", "amount_paise": 9_000}])
    home = (await a.get("/api/w/home")).json()
    assert home["today_bills"] == 1 and home["today_sales_paise"] == 9_000
