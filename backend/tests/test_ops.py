from typing import Any

import pytest
from starlette.requests import Request

from app.core.config import get_settings
from app.core.deps import client_ip
from tests.conftest import idem, make_business, owner_conn


def _request(xff: str | None, peer: str = "10.0.0.9") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1)})


@pytest.mark.parametrize(
    ("hops", "xff", "expected"),
    [
        (0, "1.1.1.1", "10.0.0.9"),  # no proxy trusted: header ignored
        (1, "6.6.6.6, 203.0.113.7", "203.0.113.7"),  # spoofed left entry ignored
        (1, "203.0.113.7", "203.0.113.7"),
        (2, "6.6.6.6, 203.0.113.7, 172.16.0.1", "203.0.113.7"),
        (1, None, "10.0.0.9"),
    ],
)
def test_client_ip_uses_trusted_hops_from_the_right(
    monkeypatch: pytest.MonkeyPatch, hops: int, xff: str | None, expected: str
) -> None:
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", hops)
    assert client_ip(_request(xff)) == expected


async def test_cleanup_removes_only_expired_technical_rows(admin_client: Any, client_factory: Any) -> None:
    from app.jobs.cleanup import run

    a, business_id = await make_business(admin_client, client_factory)
    await a.post("/api/w/locations", json={"name": "Keep"}, headers=idem())
    with owner_conn() as conn:
        conn.execute("SELECT set_config('app.business_id', %s, false)", (business_id,))
        conn.execute("UPDATE idempotency_keys SET created_at = now() - interval '8 days'")
        audit_before = conn.execute("SELECT count(*) FROM audit_events").fetchone()

    counts = await run()
    assert counts["idempotency_keys"] >= 1

    with owner_conn() as conn:
        conn.execute("SELECT set_config('app.business_id', %s, false)", (business_id,))
        assert conn.execute("SELECT count(*) FROM idempotency_keys").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM audit_events").fetchone() == audit_before
        assert conn.execute("SELECT count(*) FROM locations").fetchone() == (1,)
