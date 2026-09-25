"""Idempotency, module gating, role permissions and location restrictions."""

import asyncio
from typing import Any

from tests.conftest import idem, make_business


async def test_idempotent_replay_returns_original_and_creates_once(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    headers = idem()
    first = await a.post("/api/w/locations", json={"name": "Madhavaram"}, headers=headers)
    again = await a.post("/api/w/locations", json={"name": "Madhavaram"}, headers=headers)
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    assert again.headers.get("idempotent-replayed") == "true"
    assert [x["name"] for x in (await a.get("/api/w/locations")).json()].count("Madhavaram") == 1


async def test_concurrent_duplicates_create_once(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    headers = idem()
    results = await asyncio.gather(
        *(a.post("/api/w/locations", json={"name": "Race"}, headers=headers) for _ in range(5))
    )
    assert {r.status_code for r in results} == {201}
    assert len({r.json()["id"] for r in results}) == 1


async def test_idempotency_key_reuse_with_different_body_rejected(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    headers = idem()
    assert (await a.post("/api/w/locations", json={"name": "One"}, headers=headers)).status_code == 201
    r = await a.post("/api/w/locations", json={"name": "Two"}, headers=headers)
    assert r.status_code == 422 and r.json()["code"] == "idempotency_reused"


async def test_failed_action_does_not_burn_the_key(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    await a.post("/api/w/locations", json={"name": "Dup"}, headers=idem())
    headers = idem()
    assert (await a.post("/api/w/locations", json={"name": "Dup"}, headers=headers)).status_code == 409
    assert (await a.post("/api/w/locations", json={"name": "Dup"}, headers=headers)).status_code == 409


async def test_write_without_idempotency_key_rejected(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    assert (await a.post("/api/w/locations", json={"name": "NoKey"})).status_code == 422


async def test_disabled_module_refused_by_api(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory, modules=["sell", "bills"])
    r = await a.get("/api/w/locations")
    assert r.status_code == 403 and r.json()["code"] == "module_disabled"
    r = await a.post("/api/w/locations", json={"name": "X"}, headers=idem())
    assert r.status_code == 403
    assert (await a.get("/api/w/audit-events")).status_code == 403


async def test_viewer_cannot_manage_locations(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    viewer, _ = await make_business(admin_client, client_factory, role="viewer", business_id=business_id)
    loc = (await owner.post("/api/w/locations", json={"name": "Shop"}, headers=idem())).json()
    assert (await viewer.get(f"/api/w/locations/{loc['id']}")).status_code == 200
    r = await viewer.post("/api/w/locations", json={"name": "Nope"}, headers=idem())
    assert r.status_code == 403 and r.json()["code"] == "permission_denied"
    assert (await viewer.get("/api/w/audit-events")).status_code == 403


async def test_member_restricted_to_allowed_locations(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    shop = (await owner.post("/api/w/locations", json={"name": "Shop"}, headers=idem())).json()
    godown = (await owner.post("/api/w/locations", json={"name": "Godown"}, headers=idem())).json()
    staff, _ = await make_business(
        admin_client, client_factory, role="billing", business_id=business_id, location_ids=[shop["id"]]
    )
    assert [x["id"] for x in (await staff.get("/api/w/locations")).json()] == [shop["id"]]
    assert (await staff.get(f"/api/w/locations/{godown['id']}")).status_code == 404


async def test_update_location_records_before_and_after(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    loc = (await a.post("/api/w/locations", json={"name": "Old"}, headers=idem())).json()
    r = await a.patch(f"/api/w/locations/{loc['id']}", json={"name": "New", "name_ta": "புதிய"}, headers=idem())
    assert r.status_code == 200 and r.json()["name"] == "New"
    event = next(e for e in (await a.get("/api/w/audit-events")).json()["items"] if e["action"] == "location.update")
    assert event["before"]["name"] == "Old" and event["after"]["name"] == "New"
