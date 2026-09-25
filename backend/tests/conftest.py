"""Test harness: a real PostgreSQL 16 with the same role layout as Neon.

- ``cocreat_owner`` (not a superuser, like Neon's owner) runs the migrations;
- the API connects as ``cocreat_app``, so RLS is really exercised (superusers would bypass it).

Uses TEST_PG_ADMIN_URL (a superuser URL, e.g. the CI service container) if set, else an embedded server.
No real SMS, R2 or production database is ever touched: every value below is fake.
"""

import asyncio
import os
import secrets
import selectors
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
from sqlalchemy.engine import make_url

_server: Any = None
_admin: str = ""
TEST_DB = "cocreat_test"
ORIGIN = "http://localhost:5173"


def _admin_url() -> str:
    global _server
    if url := os.environ.get("TEST_PG_ADMIN_URL"):
        return url
    import pgserver

    _server = pgserver.get_server(tempfile.mkdtemp(prefix="cocreat-pg-"), cleanup_mode="stop")
    return str(_server.get_uri())


def pytest_configure(config: pytest.Config) -> None:
    global _admin
    _admin = _admin_url()
    admin = make_url(_admin)
    with psycopg.connect(admin.set(drivername="postgresql").render_as_string(False), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        for role in ("cocreat_app", "cocreat_owner"):
            conn.execute(
                f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
                f"EXECUTE 'DROP OWNED BY {role} CASCADE'; EXECUTE 'DROP ROLE {role}'; END IF; END $$"
            )
        conn.execute("CREATE ROLE cocreat_owner LOGIN PASSWORD 'owner-test-pw' CREATEROLE")
        conn.execute(f"CREATE DATABASE {TEST_DB} OWNER cocreat_owner")

    def url(user: str, password: str) -> str:
        return (
            admin.set(drivername="postgresql+psycopg", username=user, password=password, database=TEST_DB)
        ).render_as_string(hide_password=False)

    os.environ.update(
        APP_ENV="test",
        SESSION_SECRET=secrets.token_urlsafe(48),
        DATABASE_URL=url("cocreat_app", "app-test-pw"),
        DATABASE_URL_DIRECT=url("cocreat_owner", "owner-test-pw"),
        CORS_ORIGINS=f'["{ORIGIN}"]',
        OTP_DEV_MODE="true",
        SMS_API_KEY="fake-key",
        SMS_SENDER_ID="FAKEID",
        SMS_OTP_TEMPLATE_ID="fake-template",
        R2_ACCOUNT_ID="fake",
        R2_ACCESS_KEY_ID="fake",
        R2_SECRET_ACCESS_KEY="fake",
        R2_BUCKET="fake",
        LOG_LEVEL="WARNING",
    )

    from alembic.config import Config

    from alembic import command

    command.upgrade(Config("alembic.ini"), "head")
    with psycopg.connect(admin.set(drivername="postgresql").render_as_string(False), autocommit=True) as conn:
        conn.execute("ALTER ROLE cocreat_app LOGIN PASSWORD 'app-test-pw'")


def pytest_unconfigure(config: pytest.Config) -> None:
    if _server is not None:
        _server.cleanup()


# --- helpers ---------------------------------------------------------------------------------------------


def owner_conn() -> psycopg.Connection[Any]:
    """Direct owner connection for seeding platform rows (not RLS-protected tables only)."""
    url = make_url(os.environ["DATABASE_URL_DIRECT"]).set(drivername="postgresql")
    return psycopg.connect(url.render_as_string(hide_password=False), autocommit=True)


def superuser_conn() -> psycopg.Connection[Any]:
    """Bypasses RLS entirely, like a Neon console session would."""
    url = make_url(_admin).set(drivername="postgresql", database=TEST_DB)
    return psycopg.connect(url.render_as_string(hide_password=False), autocommit=True)


def app_conn() -> psycopg.Connection[Any]:
    """Raw connection as the API role, for proving the RLS backstop independently of the ORM."""
    url = make_url(os.environ["DATABASE_URL"]).set(drivername="postgresql")
    return psycopg.connect(url.render_as_string(hide_password=False))


def random_phone() -> str:
    return "9" + "".join(secrets.choice("0123456789") for _ in range(9))


def pytest_asyncio_loop_factories(config: pytest.Config, item: pytest.Item) -> dict[str, Any]:
    # psycopg async can't use Windows' default Proactor loop (Linux, i.e. production, is unaffected)
    if sys.platform == "win32":
        return {"selector": lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())}
    return {"default": asyncio.new_event_loop}


@pytest.fixture(scope="session")
def app() -> Any:
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
async def client_factory(app: Any) -> AsyncIterator[Any]:
    import httpx

    clients: list[httpx.AsyncClient] = []

    def make() -> httpx.AsyncClient:
        ip = f"10.{secrets.randbelow(255)}.{secrets.randbelow(255)}.{secrets.randbelow(255) + 1}"
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(ip, 12345)),
            base_url="http://test",
            headers={"Origin": ORIGIN},
        )
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()


async def login(client: Any, phone: str) -> dict[str, Any]:
    r = await client.post("/api/auth/otp/request", json={"phone": phone})
    assert r.status_code == 202, r.text
    r = await client.post("/api/auth/otp/verify", json={"challenge_id": r.json()["challenge_id"], "code": "123456"})
    assert r.status_code == 200, r.text
    me: dict[str, Any] = r.json()
    return me


def create_user(phone: str, *, admin: bool = False) -> uuid.UUID:
    with owner_conn() as conn:
        row = conn.execute(
            "INSERT INTO users (id, phone, name, language, is_platform_admin, is_active) "
            "VALUES (gen_random_uuid(), %s, 'Test User', 'en', %s, true) RETURNING id",
            (f"+91{phone}", admin),
        ).fetchone()
    assert row is not None
    return uuid.UUID(str(row[0]))


def idem() -> dict[str, str]:
    return {"Idempotency-Key": secrets.token_urlsafe(24)}


@pytest.fixture
async def admin_client(client_factory: Any) -> Any:
    client = client_factory()
    phone = random_phone()
    create_user(phone, admin=True)
    await login(client, phone)
    return client


async def make_business(
    admin_client: Any,
    client_factory: Any,
    *,
    role: str = "owner",
    modules: list[str] | None = None,
    location_ids: list[str] | None = None,
    business_id: str | None = None,
) -> tuple[Any, str]:
    """Create a business (unless given) plus a member logged in and switched to it."""
    if business_id is None:
        body: dict[str, Any] = {"name": f"Biz {secrets.token_hex(3)}", "vertical_key": "banana"}
        if modules is not None:
            body["enabled_modules"] = modules
        r = await admin_client.post("/api/admin/businesses", json=body)
        assert r.status_code == 201, r.text
        business_id = r.json()["id"]
    phone = random_phone()
    r = await admin_client.put(
        f"/api/admin/businesses/{business_id}/members",
        json={"phone": phone, "name": "Member", "role": role, "location_ids": location_ids},
    )
    assert r.status_code == 200, r.text
    client = client_factory()
    me = await login(client, phone)
    assert me["current_business_id"] == business_id  # single membership is preselected
    return client, business_id
