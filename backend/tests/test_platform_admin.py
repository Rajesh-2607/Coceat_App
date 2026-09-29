"""Admin-only platform features: vertical templates, the setup queue and cross-business user management."""

from typing import Any

from tests import factory
from tests.conftest import create_user, login, make_business, random_phone


async def test_vertical_create_and_update(admin_client: Any, client_factory: Any) -> None:
    r = await admin_client.post(
        "/api/admin/verticals",
        json={"key": "coconut", "name": "Coconut", "name_ta": "தேங்காய்", "default_modules": ["stock", "sell"]},
    )
    assert r.status_code == 201, r.text
    vertical = r.json()
    assert vertical["default_modules"] == ["sell", "stock"]

    again = await admin_client.post(
        "/api/admin/verticals", json={"key": "coconut", "name": "Coconut 2", "name_ta": "x", "default_modules": []}
    )
    assert again.status_code == 422 and again.json()["code"] == "vertical_key_taken"

    r = await admin_client.patch(
        "/api/admin/verticals/coconut", json={"name": "Coconuts", "default_modules": ["stock"]}
    )
    assert r.status_code == 200 and r.json()["name"] == "Coconuts" and r.json()["default_modules"] == ["stock"]

    missing = await admin_client.patch("/api/admin/verticals/does-not-exist", json={"name": "x"})
    assert missing.status_code == 404

    # a business created afterwards on the updated vertical picks up its (new) default modules
    r = await admin_client.post("/api/admin/businesses", json={"name": "Coco Traders", "vertical_key": "coconut"})
    assert r.status_code == 201 and r.json()["enabled_modules"] == ["stock"]


async def test_vertical_key_must_be_lowercase_slug(admin_client: Any, client_factory: Any) -> None:
    r = await admin_client.post(
        "/api/admin/verticals", json={"key": "Bad Key!", "name": "x", "name_ta": "x", "default_modules": []}
    )
    assert r.status_code == 422


async def test_verticals_require_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, _ = await make_business(admin_client, client_factory)
    r = await owner.post("/api/admin/verticals", json={"key": "x", "name": "x", "name_ta": "x", "default_modules": []})
    assert r.status_code == 403


async def test_setup_queue_and_complete_setup(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    queue = (await admin_client.get("/api/admin/setup-queue")).json()
    assert business_id in {b["id"] for b in queue}
    assert next(b for b in queue if b["id"] == business_id)["setup_completed_at"] is None

    r = await admin_client.post(f"/api/admin/businesses/{business_id}/complete-setup")
    assert r.status_code == 200 and r.json()["setup_completed_at"] is not None

    queue_after = (await admin_client.get("/api/admin/setup-queue")).json()
    assert business_id not in {b["id"] for b in queue_after}

    again = await admin_client.post(f"/api/admin/businesses/{business_id}/complete-setup")
    assert again.status_code == 422 and again.json()["code"] == "setup_already_complete"

    missing = await admin_client.post("/api/admin/businesses/00000000-0000-0000-0000-000000000000/complete-setup")
    assert missing.status_code == 404


async def test_setup_queue_excludes_suspended_businesses(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    await admin_client.patch(f"/api/admin/businesses/{business_id}", json={"status": "suspended"})
    queue = (await admin_client.get("/api/admin/setup-queue")).json()
    assert business_id not in {b["id"] for b in queue}


async def test_setup_queue_requires_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, _ = await make_business(admin_client, client_factory)
    assert (await owner.get("/api/admin/setup-queue")).status_code == 403


async def test_platform_users_list_and_search(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    users = (await admin_client.get("/api/admin/users")).json()
    member = next(u for u in users if u["memberships"] and u["memberships"][0]["business_id"] == business_id)
    assert member["memberships"][0]["role"] == "owner" and member["memberships"][0]["business_name"]

    by_phone = (await admin_client.get("/api/admin/users", params={"q": member["phone"]})).json()
    assert [u["id"] for u in by_phone] == [member["id"]]
    assert (await admin_client.get("/api/admin/users", params={"q": "no-such-phone-xyz"})).json() == []


async def test_platform_user_deactivate_locks_out_every_business(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    users = (await admin_client.get("/api/admin/users")).json()
    member = next(u for u in users if u["memberships"] and u["memberships"][0]["business_id"] == business_id)
    r = await admin_client.patch(f"/api/admin/users/{member['id']}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await owner.get("/api/w/locations")).status_code == 401


async def test_platform_admin_cannot_edit_their_own_access_here(admin_client: Any, client_factory: Any) -> None:
    users = (await admin_client.get("/api/admin/users")).json()
    me = next(u for u in users if u["is_platform_admin"])
    for body in ({"is_active": False}, {"is_platform_admin": False}):
        r = await admin_client.patch(f"/api/admin/users/{me['id']}", json=body)
        assert r.status_code == 422 and r.json()["code"] == "cannot_edit_self"
    # a field that isn't access-related is fine even on your own account
    assert (await admin_client.patch(f"/api/admin/users/{me['id']}", json={})).status_code == 200


async def test_one_platform_admin_may_demote_another(admin_client: Any, client_factory: Any) -> None:
    phone = random_phone()
    create_user(phone, admin=True)
    second_admin = client_factory()
    await login(second_admin, phone)
    users = (await admin_client.get("/api/admin/users")).json()
    second = next(u for u in users if u["phone"].endswith(phone))
    assert second["is_platform_admin"] is True

    r = await admin_client.patch(f"/api/admin/users/{second['id']}", json={"is_platform_admin": False})
    assert r.status_code == 200 and r.json()["is_platform_admin"] is False
    assert (await second_admin.get("/api/admin/setup-queue")).status_code == 403  # lost admin access immediately


async def test_platform_users_require_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, _ = await make_business(admin_client, client_factory)
    assert (await owner.get("/api/admin/users")).status_code == 403
    assert (await owner.patch("/api/admin/users/00000000-0000-0000-0000-000000000000", json={})).status_code == 403


async def test_new_business_starts_on_a_trial_subscription(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    sub = (await admin_client.get(f"/api/admin/businesses/{business_id}/subscription")).json()
    assert sub["plan_key"] == "trial" and sub["status"] == "trial" and sub["price_paise"] == 0
    assert sub["trial_ends_at"] is not None and sub["current_period_end"] is None


async def test_default_plans_are_seeded(admin_client: Any, client_factory: Any) -> None:
    plans = (await admin_client.get("/api/admin/plans")).json()
    by_key = {p["key"]: p for p in plans}
    assert {"trial", "basic", "pro", "enterprise"} <= set(by_key)
    assert by_key["trial"]["billing_period"] == "trial" and by_key["trial"]["price_paise"] == 0
    assert by_key["enterprise"]["price_paise"] is None  # contact us


async def test_admin_moves_a_business_from_trial_to_a_paid_plan(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    r = await admin_client.patch(
        f"/api/admin/businesses/{business_id}/subscription",
        json={
            "plan_key": "pro",
            "status": "active",
            "price_paise": 249_900,
            "current_period_end": "2027-01-01T00:00:00Z",
        },
    )
    assert r.status_code == 200, r.text
    sub = r.json()
    assert sub["plan_key"] == "pro" and sub["status"] == "active" and sub["price_paise"] == 249_900
    assert sub["current_period_end"] is not None and sub["cancelled_at"] is None


async def test_cancelling_a_subscription_stamps_cancelled_at_and_reactivating_clears_it(
    admin_client: Any, client_factory: Any
) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    r = await admin_client.patch(f"/api/admin/businesses/{business_id}/subscription", json={"status": "cancelled"})
    assert r.status_code == 200 and r.json()["cancelled_at"] is not None
    r = await admin_client.patch(f"/api/admin/businesses/{business_id}/subscription", json={"status": "active"})
    assert r.status_code == 200 and r.json()["cancelled_at"] is None


async def test_subscription_update_rejects_an_unknown_plan(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    r = await admin_client.patch(f"/api/admin/businesses/{business_id}/subscription", json={"plan_key": "no-such-plan"})
    assert r.status_code == 422 and r.json()["code"] == "unknown_plan"


async def test_subscription_not_found_for_missing_business(admin_client: Any, client_factory: Any) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await admin_client.get(f"/api/admin/businesses/{missing}/subscription")).status_code == 404
    r = await admin_client.patch(f"/api/admin/businesses/{missing}/subscription", json={"status": "active"})
    assert r.status_code == 404


async def test_list_subscriptions_filters_by_status_and_includes_business_name(
    admin_client: Any, client_factory: Any
) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    await admin_client.patch(
        f"/api/admin/businesses/{business_id}/subscription", json={"status": "active", "plan_key": "basic"}
    )
    active = (await admin_client.get("/api/admin/subscriptions", params={"status": "active"})).json()
    mine = next(s for s in active if s["business_id"] == business_id)
    assert mine["business_name"] and mine["plan_key"] == "basic"
    assert all(s["status"] == "active" for s in active)


async def test_subscription_stats_count_by_status_and_expiring_soon(admin_client: Any, client_factory: Any) -> None:
    _, trial_business = await make_business(admin_client, client_factory)
    _, active_business = await make_business(admin_client, client_factory)
    await admin_client.patch(
        f"/api/admin/businesses/{active_business}/subscription", json={"status": "active", "plan_key": "basic"}
    )
    before = (await admin_client.get("/api/admin/subscriptions/stats")).json()
    assert before["trial"] >= 1 and before["active"] >= 1

    r = await admin_client.patch(
        f"/api/admin/businesses/{trial_business}/subscription", json={"trial_ends_at": "2026-01-01T00:00:00Z"}
    )
    assert r.status_code == 200
    after = (await admin_client.get("/api/admin/subscriptions/stats")).json()
    assert after["expiring_soon"] >= before["expiring_soon"]


async def test_create_and_update_a_plan(admin_client: Any, client_factory: Any) -> None:
    r = await admin_client.post(
        "/api/admin/plans",
        json={
            "key": "starter",
            "name": "Starter",
            "name_ta": "தொடக்கம்",
            "price_paise": 49_900,
            "billing_period": "monthly",
        },
    )
    assert r.status_code == 201, r.text
    again = await admin_client.post(
        "/api/admin/plans",
        json={"key": "starter", "name": "x", "name_ta": "x", "price_paise": 0, "billing_period": "monthly"},
    )
    assert again.status_code == 422 and again.json()["code"] == "plan_key_taken"

    r = await admin_client.patch("/api/admin/plans/starter", json={"price_paise": 59_900, "is_active": False})
    assert r.status_code == 200 and r.json()["price_paise"] == 59_900 and r.json()["is_active"] is False
    assert (await admin_client.patch("/api/admin/plans/no-such-plan", json={"name": "x"})).status_code == 404

    active_only = (await admin_client.get("/api/admin/plans", params={"include_inactive": "false"})).json()
    assert "starter" not in {p["key"] for p in active_only}


async def test_trial_plan_without_trial_days_is_rejected(admin_client: Any, client_factory: Any) -> None:
    r = await admin_client.post(
        "/api/admin/plans",
        json={"key": "badtrial", "name": "x", "name_ta": "x", "billing_period": "trial"},
    )
    assert r.status_code == 422 and r.json()["code"] == "trial_days_required"


async def test_subscriptions_require_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    assert (await owner.get("/api/admin/plans")).status_code == 403
    assert (await owner.get("/api/admin/subscriptions")).status_code == 403
    assert (await owner.get(f"/api/admin/businesses/{business_id}/subscription")).status_code == 403
    r = await owner.patch(f"/api/admin/businesses/{business_id}/subscription", json={"status": "active"})
    assert r.status_code == 403


# --- payment_status / MRR --------------------------------------------------------------------------------


async def test_subscription_payment_status_defaults_ok_and_is_editable(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    sub = (await admin_client.get(f"/api/admin/businesses/{business_id}/subscription")).json()
    assert sub["payment_status"] == "ok"

    r = await admin_client.patch(f"/api/admin/businesses/{business_id}/subscription", json={"payment_status": "failed"})
    assert r.status_code == 200 and r.json()["payment_status"] == "failed"

    stats = (await admin_client.get("/api/admin/subscriptions/stats")).json()
    assert stats["payment_failures"] >= 1


async def test_mrr_counts_active_subscriptions_normalized_to_monthly(admin_client: Any, client_factory: Any) -> None:
    before = (await admin_client.get("/api/admin/subscriptions/stats")).json()["mrr_paise"]

    _, monthly_business = await make_business(admin_client, client_factory)
    await admin_client.patch(
        f"/api/admin/businesses/{monthly_business}/subscription",
        json={"status": "active", "plan_key": "basic", "price_paise": 120_000},
    )
    _, yearly_business = await make_business(admin_client, client_factory)
    await admin_client.post(
        "/api/admin/plans",
        json={
            "key": "yearly_test",
            "name": "Yearly",
            "name_ta": "x",
            "price_paise": 1_200_000,
            "billing_period": "yearly",
        },
    )
    await admin_client.patch(
        f"/api/admin/businesses/{yearly_business}/subscription",
        json={"status": "active", "plan_key": "yearly_test", "price_paise": 1_200_000},
    )

    after = (await admin_client.get("/api/admin/subscriptions/stats")).json()["mrr_paise"]
    # monthly business adds 120,000 as-is; yearly business adds 1,200,000 / 12 = 100,000
    assert after - before == 220_000


# --- vertical workflow steps / highlights ----------------------------------------------------------------


async def test_vertical_workflow_steps_round_trip(admin_client: Any, client_factory: Any) -> None:
    r = await admin_client.post(
        "/api/admin/verticals",
        json={
            "key": "papaya",
            "name": "Papaya",
            "name_ta": "பப்பாளி",
            "default_modules": [],
            "workflow_steps": [{"step": 1, "title": "Purchase"}, {"step": 2, "title": "Sale"}],
            "workflow_highlights": [{"title": "Perishable", "description": "Moves fast."}],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workflow_steps"] == [{"step": 1, "title": "Purchase"}, {"step": 2, "title": "Sale"}]
    assert body["workflow_highlights"] == [{"title": "Perishable", "description": "Moves fast."}]

    r = await admin_client.patch(
        "/api/admin/verticals/papaya",
        json={"workflow_steps": [{"step": 1, "title": "Only step"}]},
    )
    assert r.status_code == 200
    assert r.json()["workflow_steps"] == [{"step": 1, "title": "Only step"}]
    # untouched field is preserved
    assert r.json()["workflow_highlights"] == [{"title": "Perishable", "description": "Moves fast."}]


async def test_verticals_default_to_empty_workflow(admin_client: Any, client_factory: Any) -> None:
    r = await admin_client.post(
        "/api/admin/verticals", json={"key": "guava", "name": "Guava", "name_ta": "x", "default_modules": []}
    )
    assert r.status_code == 201
    assert r.json()["workflow_steps"] == [] and r.json()["workflow_highlights"] == []


# --- platform users: descriptive role/scope fields --------------------------------------------------------


async def test_platform_user_role_title_and_scope_note_are_editable(admin_client: Any, client_factory: Any) -> None:
    _, business_id = await make_business(admin_client, client_factory)
    users = (await admin_client.get("/api/admin/users")).json()
    member = next(u for u in users if u["memberships"] and u["memberships"][0]["business_id"] == business_id)
    assert member["platform_role_title"] is None and member["platform_scope_note"] is None

    r = await admin_client.patch(
        f"/api/admin/users/{member['id']}",
        json={"platform_role_title": "Support Engineer", "platform_scope_note": "Chennai markets"},
    )
    assert r.status_code == 200
    assert r.json()["platform_role_title"] == "Support Engineer"
    assert r.json()["platform_scope_note"] == "Chennai markets"


# --- richer admin business summary -------------------------------------------------------------------------


async def test_admin_business_list_includes_location_member_and_plan_summary(
    admin_client: Any, client_factory: Any
) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    await factory.location(owner, "Shop A")
    await admin_client.patch(
        f"/api/admin/businesses/{business_id}/subscription", json={"status": "active", "plan_key": "pro"}
    )

    rows = (await admin_client.get("/api/admin/businesses")).json()
    mine = next(b for b in rows if b["id"] == business_id)
    assert mine["location_count"] == 1
    assert mine["member_count"] >= 1  # the owner created with the business
    assert mine["plan_key"] == "pro" and mine["subscription_status"] == "active"

    detail = (await admin_client.get(f"/api/admin/businesses/{business_id}")).json()
    assert detail["location_count"] == 1 and detail["plan_key"] == "pro"


# --- platform settings (singleton) ---------------------------------------------------------------------


async def test_platform_settings_get_and_patch(admin_client: Any, client_factory: Any) -> None:
    settings = (await admin_client.get("/api/admin/settings")).json()
    assert settings["platform_name"] and settings["default_currency"] == "INR"
    assert settings["notification_prefs"]["trial_expiring"] == {"email": True, "slack": True}

    r = await admin_client.patch(
        "/api/admin/settings",
        json={
            "platform_name": "Cocreat OS",
            "grace_period_days": 10,
            "notification_prefs": {"trial_expiring": {"email": False, "slack": True}},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["platform_name"] == "Cocreat OS" and body["grace_period_days"] == 10
    assert body["notification_prefs"] == {"trial_expiring": {"email": False, "slack": True}}
    # fields not sent are unchanged
    assert body["support_email"] == settings["support_email"]

    bad = await admin_client.patch("/api/admin/settings", json={"default_plan_key": "no-such-plan"})
    assert bad.status_code == 422 and bad.json()["code"] == "unknown_plan"


async def test_platform_settings_require_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, _ = await make_business(admin_client, client_factory)
    assert (await owner.get("/api/admin/settings")).status_code == 403
    assert (await owner.patch("/api/admin/settings", json={})).status_code == 403


# --- admin locations read (cross-tenant, admin-only) -------------------------------------------------------


async def test_admin_can_list_a_businesss_locations(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    await factory.location(owner, "Shop A")
    await factory.location(owner, "Shop B")

    rows = (await admin_client.get(f"/api/admin/businesses/{business_id}/locations")).json()
    assert {r["name"] for r in rows} == {"Shop A", "Shop B"}


async def test_admin_locations_require_a_platform_admin(admin_client: Any, client_factory: Any) -> None:
    owner, business_id = await make_business(admin_client, client_factory)
    assert (await owner.get(f"/api/admin/businesses/{business_id}/locations")).status_code == 403
