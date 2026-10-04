"""The bootstrap script that gives a person their first username and password."""

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import create_user, owner_conn, random_phone


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "set_login.py"
    spec = importlib.util.spec_from_file_location("set_login", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**kw: Any) -> argparse.Namespace:
    base: dict[str, Any] = {"phone": "", "username": "", "create_platform_admin": False, "name": "Platform admin"}
    return argparse.Namespace(**{**base, **kw})


def _answer_passwords(monkeypatch: pytest.MonkeyPatch, module: ModuleType, first: str, second: str) -> None:
    answers = iter([first, second])
    monkeypatch.setattr(module.getpass, "getpass", lambda _prompt="": next(answers))


async def test_creates_the_first_platform_admin_who_can_log_in(
    monkeypatch: pytest.MonkeyPatch, client_factory: Any
) -> None:
    module = _script()
    phone = random_phone()
    username = f"first{phone[-6:]}"
    _answer_passwords(monkeypatch, module, "first-admin-pass-1", "first-admin-pass-1")
    code = await module.run(_args(phone=phone, username=username, create_platform_admin=True))
    assert code == 0
    r = await client_factory().post("/api/auth/login", json={"username": username, "password": "first-admin-pass-1"})
    assert r.status_code == 200 and r.json()["is_platform_admin"] is True


async def test_unknown_number_is_refused_without_the_create_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _script()
    _answer_passwords(monkeypatch, module, "some-password-1", "some-password-1")
    code = await module.run(_args(phone=random_phone(), username=f"nobody{random_phone()[-5:]}"))
    assert code == 1


async def test_sets_a_password_on_an_existing_account(monkeypatch: pytest.MonkeyPatch, client_factory: Any) -> None:
    module = _script()
    phone = random_phone()
    create_user(phone)
    username = f"set{phone[-6:]}"
    _answer_passwords(monkeypatch, module, "replaced-pass-123", "replaced-pass-123")
    assert await module.run(_args(phone=phone, username=username)) == 0
    r = await client_factory().post("/api/auth/login", json={"username": username, "password": "replaced-pass-123"})
    assert r.status_code == 200


async def test_taken_username_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _script()
    existing = random_phone()
    create_user(existing)  # takes the username u<phone>
    _answer_passwords(monkeypatch, module, "another-pass-1", "another-pass-1")
    code = await module.run(_args(phone=random_phone(), username=f"u{existing}", create_platform_admin=True))
    assert code == 1
    with owner_conn() as conn:
        row = conn.execute("SELECT count(*) FROM users WHERE username = %s", (f"u{existing}",)).fetchone()
    assert row is not None and row[0] == 1


async def test_mismatched_passwords_change_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _script()
    phone = random_phone()
    _answer_passwords(monkeypatch, module, "one-password-1", "two-password-2")
    code = await module.run(_args(phone=phone, username=f"mis{phone[-6:]}", create_platform_admin=True))
    assert code == 2
    with owner_conn() as conn:
        row = conn.execute("SELECT count(*) FROM users WHERE phone = %s", (f"+91{phone}",)).fetchone()
    assert row is not None and row[0] == 0
