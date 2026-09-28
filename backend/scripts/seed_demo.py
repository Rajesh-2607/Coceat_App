"""Seed a LOCAL dev API with two demo businesses (banana and tomato traders) through its real endpoints.

Usage (API running locally with OTP_DEV_MODE=true and a platform admin user already in the database):

    uv run python scripts/seed_demo.py --api http://localhost:8000 --admin-phone <10-digit admin number>

It only talks HTTP, so every rule (permissions, tenancy, audit, idempotency) applies exactly as in the app.
Safe to re-run: a business whose name already exists is skipped. It refuses to run against non-local URLs.
All names and numbers below are made up.
"""

import argparse
import secrets
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

ORIGIN = "http://localhost:5173"  # the CSRF check wants the frontend's origin
DEV_OTP = "123456"  # only valid when the API runs with OTP_DEV_MODE=true

# id numbers are sequential placeholders, not real people
PEOPLE = {
    "owner": ("9000000011", "Kumaravel"),
    "manager": ("9000000012", "Selvi"),
    "billing": ("9000000013", "Murugan"),
    "stock": ("9000000014", "Ravi"),
    "tomato_owner": ("9000000021", "Anbu"),
}


class Api:
    def __init__(self, base: str) -> None:
        self.http = httpx.Client(base_url=base, headers={"Origin": ORIGIN}, timeout=30)

    def login(self, phone: str) -> None:
        r = self.http.post("/api/auth/otp/request", json={"phone": phone})
        r.raise_for_status()
        r = self.http.post("/api/auth/otp/verify", json={"challenge_id": r.json()["challenge_id"], "code": DEV_OTP})
        r.raise_for_status()

    def get(self, url: str, **params: Any) -> Any:
        r = self.http.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def post(self, url: str, body: dict[str, Any], *, key: bool = True) -> Any:
        headers = {"Idempotency-Key": secrets.token_urlsafe(24)} if key else {}
        r = self.http.post(url, json=body, headers=headers)
        if r.status_code >= 400:
            sys.exit(f"POST {url} failed: {r.status_code} {r.text}")
        return r.json()

    def patch(self, url: str, body: dict[str, Any]) -> Any:
        r = self.http.patch(url, json=body)
        r.raise_for_status()
        return r.json()

    def put(self, url: str, body: dict[str, Any]) -> Any:
        r = self.http.put(url, json=body)
        r.raise_for_status()
        return r.json()


def rupees(amount: float) -> int:
    return round(amount * 100)


def ensure_business(admin: Api, name: str, name_ta: str, vertical: str, gstin: str | None) -> tuple[str, bool]:
    for b in admin.get("/api/admin/businesses"):
        if b["name"] == name:
            return b["id"], False
    b = admin.post(
        "/api/admin/businesses", {"name": name, "name_ta": name_ta, "vertical_key": vertical, "gstin": gstin}, key=False
    )
    return b["id"], True


def add_member(admin: Api, business_id: str, key: str, role: str, location_ids: list[str] | None = None) -> None:
    phone, name = PEOPLE[key]
    admin.put(
        f"/api/admin/businesses/{business_id}/members",
        {"phone": phone, "name": name, "role": role, "location_ids": location_ids},
    )


def seed_banana(admin: Api, api_url: str) -> None:
    business_id, created = ensure_business(
        admin, "ABC Banana Traders", "ஏபிசி வாழைப்பழ வியாபாரிகள்", "banana", "33ABCDE1234F1Z5"
    )
    if not created:
        print("ABC Banana Traders already exists: skipped")
        return
    add_member(admin, business_id, "owner", "owner")
    owner = Api(api_url)
    owner.login(PEOPLE["owner"][0])

    shop = owner.post("/api/w/locations", {"name": "Koyambedu Shop", "name_ta": "கோயம்பேடு கடை", "kind": "shop"})
    godown = owner.post("/api/w/locations", {"name": "Madhavaram Godown", "name_ta": "மாதவரம் கிடங்கு", "kind": "godown"})
    cold = owner.post("/api/w/locations", {"name": "Cold Storage", "name_ta": "குளிர் சேமிப்பு", "kind": "cold_storage"})

    add_member(admin, business_id, "manager", "manager")
    add_member(admin, business_id, "billing", "billing", [shop["id"]])
    add_member(admin, business_id, "stock", "stock", [godown["id"]])

    units = {u["code"]: u for u in owner.get("/api/w/units")}
    grades = {g: owner.post("/api/w/grades", {"name": g, "name_ta": f"தரம் {g}"}) for g in ("A", "B", "C")}

    def product(
        name: str, name_ta: str, price: float, varieties: list[tuple[str, str]], *, kind: str = "weight"
    ) -> dict[str, Any]:
        unit = units["kg" if kind == "weight" else "piece"]
        p = owner.post(
            "/api/w/products",
            {
                "name": name,
                "name_ta": name_ta,
                "kind": kind,
                "unit_id": unit["id"],
                "default_price_paise": rupees(price),
            },
        )
        p["varieties"] = [
            owner.post(f"/api/w/products/{p['id']}/varieties", {"name": n, "name_ta": ta}) for n, ta in varieties
        ]
        return p

    banana = product(
        "Banana",
        "வாழைப்பழம்",
        45,
        [("Robusta", "ரோபஸ்டா"), ("Poovan", "பூவன்"), ("Nendran", "நேந்திரன்"), ("Red banana", "செவ்வாழை")],
    )
    raw = product("Raw banana", "வாழைக்காய்", 32, [("Nadan", "நாடன்")])
    leaf = product("Banana leaf", "வாழை இலை", 6, [], kind="count")

    def stock(
        loc: dict[str, Any],
        prod: dict[str, Any],
        variety: int | None,
        grade: str | None,
        kg: float | None = None,
        pcs: int | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "location_id": loc["id"],
            "product_id": prod["id"],
            "quantity": round(kg * 1000) if kg is not None else pcs,
            "note": "Opening stock",
        }
        if variety is not None:
            body["variety_id"] = prod["varieties"][variety]["id"]
        if grade:
            body["grade_id"] = grades[grade]["id"]
        owner.post("/api/w/stock/opening", body)

    stock(godown, banana, 0, "A", kg=1200)
    stock(godown, banana, 1, "A", kg=800)
    stock(godown, banana, 2, "B", kg=450)
    stock(shop, banana, 0, "A", kg=180)
    stock(shop, banana, 1, "B", kg=95.5)
    stock(cold, banana, 3, "A", kg=260)
    stock(godown, raw, 0, None, kg=600)
    stock(shop, leaf, None, None, pcs=2000)

    owner.post(
        "/api/w/stock/transfers",
        {
            "from_location_id": godown["id"],
            "to_location_id": shop["id"],
            "note": "Morning refill",
            "lines": [
                {
                    "product_id": banana["id"],
                    "variety_id": banana["varieties"][0]["id"],
                    "grade_id": grades["A"]["id"],
                    "quantity": 300_000,
                }
            ],
        },
    )
    owner.post(
        "/api/w/stock/wastage",
        {
            "location_id": shop["id"],
            "product_id": banana["id"],
            "variety_id": banana["varieties"][1]["id"],
            "grade_id": grades["B"]["id"],
            "quantity": 4_500,
            "reason_code": "rotten",
            "note": "Overripe, found at closing",
        },
    )

    customers = [
        ("Chennai Fresh Mart", "சென்னை ஃப்ரெஷ் மார்ட்", "9000001001", 24500, 100_000, 12),
        ("Anand Hotel", "ஆனந்த் ஹோட்டல்", "9000001002", 18000, 50_000, 6),
        ("Lakshmi Stores", "லக்ஷ்மி ஸ்டோர்ஸ்", "9000001003", 0, 30_000, 0),
        ("Raja Juice Corner", "ராஜா ஜூஸ் கார்னர்", "9000001004", 10000, 20_000, 3),
    ]
    for name, name_ta, phone, owed, limit, crates in customers:
        c = owner.post(
            "/api/w/customers",
            {
                "name": name,
                "name_ta": name_ta,
                "phone": phone,
                "credit_limit_paise": rupees(limit),
                "opening_balance_paise": rupees(owed),
            },
        )
        if crates:
            owner.post(
                "/api/w/crates/entries",
                {"party_id": c["id"], "direction": "issued", "quantity": crates, "location_id": shop["id"]},
            )

    suppliers = [
        ("Theni Banana Farms", "தேனி வாழைப் பண்ணை", "9000002001", -47500),
        ("Kanyakumari Growers", "கன்னியாகுமரி விவசாயிகள்", "9000002002", 0),
    ]
    for name, name_ta, phone, balance in suppliers:
        owner.post(
            "/api/w/suppliers",
            {"name": name, "name_ta": name_ta, "phone": phone, "opening_balance_paise": rupees(balance)},
        )
    print("Seeded ABC Banana Traders")


def seed_tomato(admin: Api, api_url: str) -> None:
    business_id, created = ensure_business(admin, "Tomato Traders", "தக்காளி வியாபாரிகள்", "tomato", None)
    if not created:
        print("Tomato Traders already exists: skipped")
        return
    add_member(admin, business_id, "tomato_owner", "owner")
    owner = Api(api_url)
    owner.login(PEOPLE["tomato_owner"][0])
    shop = owner.post("/api/w/locations", {"name": "Koyambedu Market", "name_ta": "கோயம்பேடு சந்தை", "kind": "shop"})
    kg = next(u for u in owner.get("/api/w/units") if u["code"] == "kg")
    tomato = owner.post(
        "/api/w/products",
        {
            "name": "Tomato",
            "name_ta": "தக்காளி",
            "kind": "weight",
            "unit_id": kg["id"],
            "default_price_paise": rupees(28),
        },
    )
    owner.post(
        "/api/w/stock/opening",
        {"location_id": shop["id"], "product_id": tomato["id"], "quantity": 2_400_000, "note": "Opening stock"},
    )
    owner.post(
        "/api/w/customers", {"name": "Sri Vegetables", "phone": "9000003001", "opening_balance_paise": rupees(52500)}
    )
    print("Seeded Tomato Traders")


def seed_trading(admin: Api, api_url: str) -> None:
    """A little trading history for ABC Banana Traders: a purchase, bills (one with GST), a payment. Runs once."""
    business = next((b for b in admin.get("/api/admin/businesses") if b["name"] == "ABC Banana Traders"), None)
    if business is None:
        return
    admin.patch(
        f"/api/admin/businesses/{business['id']}",
        {"address": "Shop 14, Koyambedu Wholesale Market, Chennai 600092", "phone": "9000000010"},
    )
    owner = Api(api_url)
    owner.login(PEOPLE["owner"][0])
    if owner.get("/api/w/bills"):
        print("ABC Banana Traders already has bills: trading history skipped")
        return

    products = {p["name"]: p for p in owner.get("/api/w/products")}
    units = {u["code"]: u for u in owner.get("/api/w/units")}
    locations = {loc["name"]: loc for loc in owner.get("/api/w/locations")}
    grades = {g["name"]: g for g in owner.get("/api/w/grades")}
    customers = {c["name"]: c for c in owner.get("/api/w/customers")}
    suppliers = {s["name"]: s for s in owner.get("/api/w/suppliers")}
    shop, godown = locations["Koyambedu Shop"], locations["Madhavaram Godown"]
    banana, leaf = products["Banana"], products["Banana leaf"]
    varieties = {v["name"]: v for v in banana["varieties"]}

    owner.post(
        "/api/w/purchases",
        {
            "supplier_id": suppliers["Theni Banana Farms"]["id"],
            "location_id": godown["id"],
            "supplier_bill_no": "TBF-2231",
            "lines": [
                {
                    "product_id": banana["id"],
                    "variety_id": varieties["Robusta"]["id"],
                    "grade_id": grades["A"]["id"],
                    "unit_id": units["kg"]["id"],
                    "quantity": 500_000,
                    "unit_cost_paise": rupees(32),
                }
            ],
            "payments": [{"method": "upi", "amount_paise": rupees(6_000)}],
        },
    )

    def line(prod: dict[str, Any], unit: str, qty: int, price: float, **item: str) -> dict[str, Any]:
        return {
            "product_id": prod["id"],
            "unit_id": units[unit]["id"],
            "quantity": qty,
            "unit_price_paise": rupees(price),
            **item,
        }

    def bill(lines: list[dict[str, Any]], payments: list[dict[str, Any]], party: str | None = None) -> None:
        body: dict[str, Any] = {"location_id": shop["id"], "lines": lines, "payments": payments}
        if party:
            body["party_id"] = customers[party]["id"]
        owner.post("/api/w/bills", body)

    robusta_a = {"variety_id": varieties["Robusta"]["id"], "grade_id": grades["A"]["id"]}
    poovan_b = {"variety_id": varieties["Poovan"]["id"], "grade_id": grades["B"]["id"]}
    bill([line(banana, "kg", 5_000, 45, **robusta_a)], [{"method": "cash", "amount_paise": rupees(225)}])
    bill(
        [line(banana, "kg", 20_000, 48, **poovan_b)],
        [{"method": "cash", "amount_paise": rupees(300)}],
        "Chennai Fresh Mart",
    )
    bill([line(leaf, "piece", 100, 6)], [{"method": "upi", "amount_paise": rupees(600)}], "Anand Hotel")

    # a packed product that carries 12% GST, so the demo also shows a tax invoice with CGST + SGST
    chips = owner.post(
        "/api/w/products",
        {
            "name": "Banana chips (packed)",
            "name_ta": "வாழைச் சிப்ஸ் (பாக்கெட்)",
            "kind": "count",
            "unit_id": units["piece"]["id"],
            "default_price_paise": rupees(40),
            "gst_rate_bp": 1200,
            "hsn_code": "2008",
        },
    )
    owner.post("/api/w/stock/opening", {"location_id": shop["id"], "product_id": chips["id"], "quantity": 200})
    bill([line(chips, "piece", 25, 40)], [{"method": "upi", "amount_paise": rupees(1_120)}], "Raja Juice Corner")

    owner.post(
        "/api/w/money/payments",
        {
            "party_id": customers["Anand Hotel"]["id"],
            "direction": "in",
            "method": "upi",
            "amount_paise": rupees(5_000),
            "note": "part payment",
        },
    )
    print("Seeded trading history for ABC Banana Traders")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--admin-phone", required=True, help="a platform admin that already exists in the database")
    args = parser.parse_args()
    host = urlparse(args.api).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        sys.exit("Refusing to seed a non-local API.")

    admin = Api(args.api)
    admin.login(args.admin_phone)
    seed_banana(admin, args.api)
    seed_tomato(admin, args.api)
    seed_trading(admin, args.api)
    print("Done. Log in with any seeded number (OTP 123456 in dev): owner 9000000011, tomato owner 9000000021.")


if __name__ == "__main__":
    main()
