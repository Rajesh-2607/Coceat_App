from typing import Any

import pytest

from tests.conftest import create_user, login, random_phone


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
    cid = (await c.post("/api/auth/otp/request", json={"phone": phone})).json()["challenge_id"]
    r = await c.post("/api/auth/otp/verify", json={"challenge_id": cid, "code": "123456"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith("cc_session=") and "httponly" in cookie and "samesite=lax" in cookie
    me = r.json()
    assert me["memberships"] == [] and me["current_business_id"] is None
    r = await c.get("/api/me")
    assert r.status_code == 200 and r.json()["id"] == me["id"]


async def test_unknown_phone_gets_identical_response_but_cannot_log_in(client_factory: Any) -> None:
    c = client_factory()
    r = await c.post("/api/auth/otp/request", json={"phone": random_phone()})
    assert r.status_code == 202 and set(r.json()) == {"challenge_id", "expires_in_seconds"}
    r = await c.post("/api/auth/otp/verify", json={"challenge_id": r.json()["challenge_id"], "code": "123456"})
    assert r.status_code == 401 and r.json()["code"] == "otp_invalid"


async def test_invalid_phone_rejected(client_factory: Any) -> None:
    r = await client_factory().post("/api/auth/otp/request", json={"phone": "12345678901"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_phone"


async def test_wrong_otp_locks_after_five_attempts(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    cid = (await c.post("/api/auth/otp/request", json={"phone": phone})).json()["challenge_id"]
    for _ in range(5):
        r = await c.post("/api/auth/otp/verify", json={"challenge_id": cid, "code": "000000"})
        assert r.status_code == 401
    r = await c.post("/api/auth/otp/verify", json={"challenge_id": cid, "code": "123456"})
    assert r.status_code == 429 and r.json()["code"] == "otp_locked"


async def test_otp_is_single_use(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    create_user(phone)
    cid = (await c.post("/api/auth/otp/request", json={"phone": phone})).json()["challenge_id"]
    assert (await c.post("/api/auth/otp/verify", json={"challenge_id": cid, "code": "123456"})).status_code == 200
    r = await c.post("/api/auth/otp/verify", json={"challenge_id": cid, "code": "123456"})
    assert r.status_code == 401


async def test_otp_rate_limited_per_phone(client_factory: Any) -> None:
    c = client_factory()
    phone = random_phone()
    for _ in range(3):
        assert (await c.post("/api/auth/otp/request", json={"phone": phone})).status_code == 202
    r = await c.post("/api/auth/otp/request", json={"phone": phone})
    assert r.status_code == 429 and r.json()["code"] == "otp_rate_limited"


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
        ({"OTP_DEV_MODE": "true"}, "OTP_DEV_MODE"),
        ({"OTP_DEV_MODE": "false", "SESSION_SECRET": "short"}, "SESSION_SECRET"),
        ({"OTP_DEV_MODE": "false", "CORS_ORIGINS": '["http://app.example"]'}, "CORS_ORIGINS"),
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
