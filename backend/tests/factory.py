"""Small API helpers shared by the module tests."""

from typing import Any

from tests.conftest import idem

GRAM_PER_KG = 1000


async def post(client: Any, url: str, body: dict[str, Any], *, expect: int = 201) -> Any:
    r = await client.post(url, json=body, headers=idem())
    assert r.status_code == expect, f"{url} -> {r.status_code} {r.text}"
    return r.json()


async def location(client: Any, name: str = "Shop") -> dict[str, Any]:
    body: dict[str, Any] = await post(client, "/api/w/locations", {"name": name, "kind": "shop"})
    return body


async def unit(client: Any, code: str) -> dict[str, Any]:
    units = (await client.get("/api/w/units")).json()
    return next(u for u in units if u["code"] == code)


async def product(
    client: Any, name: str = "Banana", *, kind: str = "weight", unit_code: str | None = None, **extra: Any
) -> Any:
    u = await unit(client, unit_code or ("kg" if kind == "weight" else "piece"))
    return await post(client, "/api/w/products", {"name": name, "kind": kind, "unit_id": u["id"], **extra})


async def grade(client: Any, name: str = "A") -> Any:
    return await post(client, "/api/w/grades", {"name": name})


async def customer(client: Any, name: str = "Ravi", **extra: Any) -> Any:
    return await post(client, "/api/w/customers", {"name": name, **extra})


async def supplier(client: Any, name: str = "Farm Co", **extra: Any) -> Any:
    return await post(client, "/api/w/suppliers", {"name": name, **extra})


async def opening(client: Any, loc: str, prod: str, qty: int, **extra: Any) -> Any:
    return await post(
        client, "/api/w/stock/opening", {"location_id": loc, "product_id": prod, "quantity": qty, **extra}
    )


async def balances(client: Any, **params: str) -> list[dict[str, Any]]:
    r = await client.get("/api/w/stock/balances", params=params)
    assert r.status_code == 200, r.text
    rows: list[dict[str, Any]] = r.json()
    return rows


def line(
    prod: dict[str, Any], kg_unit: dict[str, Any], grams: int, price_rupees: float, **extra: Any
) -> dict[str, Any]:
    """A sale/purchase line: ``grams`` of a weight product priced in rupees per kg."""
    return {
        "product_id": prod["id"],
        "unit_id": kg_unit["id"],
        "quantity": grams,
        "unit_price_paise": round(price_rupees * 100),
        **extra,
    }


async def sell(
    client: Any, loc: dict[str, Any], lines: list[dict[str, Any]], *, expect: int = 201, **extra: Any
) -> Any:
    body = {"location_id": loc["id"], "lines": lines, **extra}
    r = await client.post("/api/w/bills", json=body, headers=idem())
    assert r.status_code == expect, f"sell -> {r.status_code} {r.text}"
    return r.json()


async def party_balance(client: Any, kind: str, party_id: str) -> int:
    balance: int = (await client.get(f"/api/w/{kind}/{party_id}")).json()["balance_paise"]
    return balance


async def stock_of(client: Any, prod: dict[str, Any], loc: dict[str, Any]) -> int:
    rows = await balances(client, location_id=loc["id"], product_id=prod["id"])
    return sum(r["quantity"] for r in rows)
