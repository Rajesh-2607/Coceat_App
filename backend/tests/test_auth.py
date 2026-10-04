from typing import Any

import pytest

from tests.conftest import TEST_PASSWORD, create_user, login, owner_conn, random_phone, username_for


async def test_health(client_factory: Any) -> None:
    c = client_factory()
    assert (await c.get("/healthz")).json() == {"status": "ok"}
    assert (await c.get("/readyz")).status_code == 200


async def test_security_headers(client_factory: Any) -> None:
    r = await client_factory().get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-request-id"]


async def test_login_sets_httponly_cookie_and_me_works(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    r = await c.post("/api/auth/login", json={"username": username_for(phone), "password": TEST_PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith("cc_session=") and "httponly" in cookie and "samesite=lax" in cookie
    me = r.json()
    assert me["memberships"] == [] and me["current_business_id"] is None
    r = await c.get("/api/me")
    assert r.status_code == 200 and r.json()["id"] == me["id"]


async def test_username_is_case_insensitive_and_trimmed(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    username = f"  {username_for(phone).upper()} "
    r = await c.post("/api/auth/login", json={"username": username, "password": TEST_PASSWORD})
    assert r.status_code == 200


async def test_wrong_password_and_unknown_username_look_identical(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    wrong_password = await c.post("/api/auth/login", json={"username": username_for(phone), "password": "not-it-12345"})
    unknown_user = await c.post("/api/auth/login", json={"username": "nobody-here", "password": TEST_PASSWORD})
    for r in (wrong_password, unknown_user):
        assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    assert wrong_password.json() == unknown_user.json()


async def test_account_without_a_password_cannot_log_in(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    with owner_conn() as conn:
        conn.execute("UPDATE users SET password_hash = NULL WHERE username = %s", (username_for(phone),))
    r = await c.post("/api/auth/login", json={"username": username_for(phone), "password": TEST_PASSWORD})
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"


async def test_short_username_rejected_before_lookup(client_factory: Any) -> None:
    r = await client_factory().post("/api/auth/login", json={"username": "ab", "password": TEST_PASSWORD})
    assert r.status_code == 422


async def test_five_wrong_passwords_lock_the_account(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    for _ in range(5):
        r = await c.post("/api/auth/login", json={"username": username_for(phone), "password": "wrong-guess-1"})
        assert r.status_code == 401
    # even the right password is refused while the lock is active
    r = await c.post("/api/auth/login", json={"username": username_for(phone), "password": TEST_PASSWORD})
    assert r.status_code == 429 and r.json()["code"] == "account_locked"


async def test_successful_login_resets_the_failure_count(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    for _ in range(4):
        await c.post("/api/auth/login", json={"username": username_for(phone), "password": "wrong-guess-1"})
    await login(c, phone)
    for _ in range(4):
        r = await c.post("/api/auth/login", json={"username": username_for(phone), "password": "wrong-guess-1"})
        assert r.status_code == 401  # the earlier four were forgotten, so this is not a lockout yet


async def test_password_change_requires_the_current_password(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    await login(c, phone)
    r = await c.post("/api/me/password", json={"current_password": "not-it-12345", "new_password": "brand-new-pass-1"})
    assert r.status_code == 422 and r.json()["code"] == "wrong_current_password"


async def test_password_change_takes_effect_for_next_login(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    await login(c, phone)
    new_password = "brand-new-pass-1"
    r = await c.post("/api/me/password", json={"current_password": TEST_PASSWORD, "new_password": new_password})
    assert r.status_code == 204
    other = client_factory()
    r = await other.post("/api/auth/login", json={"username": username_for(phone), "password": TEST_PASSWORD})
    assert r.status_code == 401
    await login(other, phone, password=new_password)


async def test_new_password_must_meet_minimum_length(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    await login(c, phone)
    r = await c.post("/api/me/password", json={"current_password": TEST_PASSWORD, "new_password": "short"})
    assert r.status_code == 422


async def test_logout_revokes_session(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    await login(c, phone)
    cookie = c.cookies.get("cc_session")
    assert (await c.post("/api/auth/logout")).status_code == 204
    c.cookies.set("cc_session", cookie)  # replaying the old token must not work
    assert (await c.get("/api/me")).status_code == 401


async def test_unauthenticated_requests_rejected(client_factory: Any) -> None:
    c = client_factory()
    assert (await c.get("/api/me")).status_code == 401
    assert (await c.get("/api/w/locations")).status_code == 401
    assert (await c.get("/api/admin/businesses")).status_code == 401


async def test_csrf_foreign_origin_rejected(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    await login(c, phone)
    r = await c.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_origin"


async def test_non_admin_cannot_use_admin_api(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    await login(c, phone)
    r = await c.post("/api/admin/businesses", json={"name": "X", "vertical_key": "banana"})
    assert r.status_code == 403


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SESSION_SECRET": "short"}, "SESSION_SECRET"),
        ({"CORS_ORIGINS": '["http://app.example"]'}, "CORS_ORIGINS"),
    ],
)
def test_production_refuses_unsafe_settings(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], message: str
) -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.example"]')
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None)  # type: ignore[call-arg]
