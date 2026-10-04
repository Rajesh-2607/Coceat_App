"""Units, grades, products and varieties."""

from typing import Any

from tests import factory
from tests.conftest import idem, make_business


async def test_default_units_are_seeded_for_a_new_business(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    codes = {u["code"]: u for u in (await a.get("/api/w/units")).json()}
    assert {"kg", "quintal", "tonne", "piece", "dozen", "crate"} <= set(codes)
    assert codes["kg"]["kind"] == "weight" and codes["kg"]["base_factor"] == 1000  # grams
    assert codes["dozen"]["kind"] == "count" and codes["dozen"]["base_factor"] == 12


async def test_create_and_update_product_with_varieties(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    kg = await factory.unit(a, "kg")
    p = await factory.post(
        a,
        "/api/w/products",
        {"name": "Banana", "name_ta": "வாழைப்பழம்", "kind": "weight", "unit_id": kg["id"], "default_price_paise": 4500},
    )
    assert p["default_price_paise"] == 4500 and p["varieties"] == []
    v = await factory.post(a, f"/api/w/products/{p['id']}/varieties", {"name": "Robusta", "name_ta": "ரோபஸ்டா"})
    assert v["product_id"] == p["id"]
    r = await a.patch(
        f"/api/w/products/{p['id']}", json={"default_price_paise": None, "is_active": False}, headers=idem()
    )
    assert r.status_code == 200 and r.json()["default_price_paise"] is None and r.json()["is_active"] is False
    assert (await a.get("/api/w/products")).json() == []  # inactive hidden by default
    listed = (await a.get("/api/w/products", params={"include_inactive": "true"})).json()
    assert listed[0]["varieties"][0]["name"] == "Robusta"


async def test_unit_must_match_product_kind(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    piece = await factory.unit(a, "piece")
    r = await a.post(
        "/api/w/products", json={"name": "Mango", "kind": "weight", "unit_id": piece["id"]}, headers=idem()
    )
    assert r.status_code == 422 and r.json()["code"] == "unit_kind_mismatch"


async def test_duplicate_names_conflict(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    p = await factory.product(a, "Tomato")
    kg = await factory.unit(a, "kg")
    r = await a.post("/api/w/products", json={"name": "Tomato", "kind": "weight", "unit_id": kg["id"]}, headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "product_name_taken"
    await factory.post(a, f"/api/w/products/{p['id']}/varieties", {"name": "Hybrid"})
    r = await a.post(f"/api/w/products/{p['id']}/varieties", json={"name": "Hybrid"}, headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "variety_name_taken"
    await factory.grade(a, "A")
    r = await a.post("/api/w/grades", json={"name": "A"}, headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "grade_name_taken"
    r = await a.post(
        "/api/w/units", json={"code": "kg", "name": "dup", "kind": "weight", "base_factor": 1000}, headers=idem()
    )
    assert r.status_code == 409 and r.json()["code"] == "unit_code_taken"


async def test_catalog_isolated_between_businesses(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    p = await factory.product(a, "Secret product")
    g = await factory.grade(a, "Secret grade")
    kg_a = await factory.unit(a, "kg")
    assert (await b.get(f"/api/w/products/{p['id']}")).status_code == 404
    assert (await b.patch(f"/api/w/products/{p['id']}", json={"name": "x"}, headers=idem())).status_code == 404
    r = await b.post(f"/api/w/products/{p['id']}/varieties", json={"name": "x"}, headers=idem())
    assert r.status_code == 404
    assert (await b.patch(f"/api/w/grades/{g['id']}", json={"name": "x"}, headers=idem())).status_code == 404
    assert (await b.patch(f"/api/w/units/{kg_a['id']}", json={"name": "x"}, headers=idem())).status_code == 404
    assert (await b.get("/api/w/products")).json() == []
    # A product cannot be built on another business's unit
    r = await b.post("/api/w/products", json={"name": "P", "kind": "weight", "unit_id": kg_a["id"]}, headers=idem())
    assert r.status_code == 422 and r.json()["code"] == "unknown_unit"


async def test_permissions_and_module_gate(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    await factory.product(owner, "Visible")
    assert len((await viewer.get("/api/w/products")).json()) == 1
    kg = await factory.unit(viewer, "kg")
    r = await viewer.post("/api/w/products", json={"name": "No", "kind": "weight", "unit_id": kg["id"]}, headers=idem())
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    no_stock, _ = await make_business(admin_client, client_factory, modules=["sell"])
    assert (await no_stock.get("/api/w/products")).json()["code"] == "module_disabled"
