"""Tenant isolation: Business A must never see or touch Business B's data (API, ORM and RLS layers)."""

import uuid
from typing import Any

import psycopg
import pytest

from tests.conftest import (
    app_conn,
    idem,
    login,
    make_business,
    owner_conn,
    random_phone,
    superuser_conn,
)


async def _create_location(client: Any, name: str = "Koyambedu shop") -> dict[str, Any]:
    r = await client.post("/api/w/locations", json={"name": name, "kind": "shop"}, headers=idem())
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def test_business_a_gets_404_for_business_b_ids(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    loc_a = await _create_location(a)

    assert (await b.get(f"/api/w/locations/{loc_a['id']}")).status_code == 404
    r = await b.patch(f"/api/w/locations/{loc_a['id']}", json={"name": "hijacked"}, headers=idem())
    assert r.status_code == 404
    assert loc_a["id"] not in {x["id"] for x in (await b.get("/api/w/locations")).json()}
    # A still sees its own, unchanged
    assert (await a.get(f"/api/w/locations/{loc_a['id']}")).json()["name"] == "Koyambedu shop"


async def test_same_name_allowed_across_businesses_but_not_within(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    await _create_location(a, "Main")
    await _create_location(b, "Main")
    r = await a.post("/api/w/locations", json={"name": "Main"}, headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "location_name_taken"


async def test_cannot_switch_to_business_without_membership(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    _, business_b = await make_business(admin_client, client_factory)
    r = await a.put("/api/me/business", json={"business_id": business_b})
    assert r.status_code == 403 and r.json()["code"] == "not_a_member"


async def test_member_of_two_businesses_switches_explicitly(admin_client: Any, client_factory: Any) -> None:
    _, business_a = await make_business(admin_client, client_factory)
    _, business_b = await make_business(admin_client, client_factory)
    phone = random_phone()
    for biz in (business_a, business_b):
        r = await admin_client.put(
            f"/api/admin/businesses/{biz}/members", json={"phone": phone, "name": "Both", "role": "owner"}
        )
        assert r.status_code == 200
    c = client_factory()
    me = await login(c, phone)
    assert me["current_business_id"] is None and len(me["memberships"]) == 2
    assert (await c.get("/api/w/locations")).json()["code"] == "no_current_business"
    assert (await c.put("/api/me/business", json={"business_id": business_b})).status_code == 200
    ctx = (await c.get("/api/w/context")).json()
    assert ctx["business"]["id"] == business_b and ctx["role"] == "owner"


async def test_suspended_business_locks_out_members(admin_client: Any, client_factory: Any) -> None:
    a, business_a = await make_business(admin_client, client_factory)
    with owner_conn() as conn:
        conn.execute("UPDATE businesses SET status = 'suspended' WHERE id = %s", (business_a,))
    assert (await a.get("/api/w/locations")).status_code == 401


async def test_rls_blocks_raw_sql_across_tenants(admin_client: Any, client_factory: Any) -> None:
    a, business_a = await make_business(admin_client, client_factory)
    b, business_b = await make_business(admin_client, client_factory)
    await _create_location(a, "A-only")
    await _create_location(b, "B-only")

    with app_conn() as conn:
        # no business set: nothing visible
        assert conn.execute("SELECT count(*) FROM locations").fetchone() == (0,)
        conn.rollback()
        conn.execute("SELECT set_config('app.business_id', %s, true)", (business_b,))
        names = {r[0] for r in conn.execute("SELECT name FROM locations").fetchall()}
        assert "B-only" in names and "A-only" not in names
        # cannot write a row into another tenant
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO locations (id, business_id, name, kind, is_active) "
                "VALUES (%s, %s, 'sneaky', 'shop', true)",
                (uuid.uuid4(), business_a),
            )
        conn.rollback()


async def test_audit_log_is_append_only(admin_client: Any, client_factory: Any) -> None:
    a, business_a = await make_business(admin_client, client_factory)
    await _create_location(a, "Audited")
    events = (await a.get("/api/w/audit-events")).json()["items"]
    actions = [e["action"] for e in events]
    assert "location.create" in actions and "business.create" in actions
    created = next(e for e in events if e["action"] == "location.create")
    assert created["after"]["name"] == "Audited" and created["before"] is None

    with app_conn() as conn:
        conn.execute("SELECT set_config('app.business_id', %s, true)", (business_a,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM audit_events WHERE business_id = %s", (business_a,))
        conn.rollback()
    with owner_conn() as conn:  # the owner is bound by FORCE RLS: no UPDATE/DELETE policy exists
        conn.execute("SELECT set_config('app.business_id', %s, false)", (business_a,))
        assert conn.execute("UPDATE audit_events SET action = 'x' WHERE business_id = %s", (business_a,)).rowcount == 0
    with superuser_conn() as conn:  # roles that bypass RLS still hit the trigger
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("UPDATE audit_events SET action = 'x' WHERE business_id = %s", (business_a,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("DELETE FROM audit_events WHERE business_id = %s", (business_a,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
            conn.execute("TRUNCATE audit_events")


async def test_audit_events_not_visible_across_tenants(admin_client: Any, client_factory: Any) -> None:
    a, _ = await make_business(admin_client, client_factory)
    b, _ = await make_business(admin_client, client_factory)
    loc = await _create_location(a, "Secret")
    events_b = (await b.get("/api/w/audit-events")).json()["items"]
    assert all(e["entity_id"] != loc["id"] for e in events_b)
