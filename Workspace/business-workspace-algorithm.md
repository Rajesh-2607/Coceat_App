# Business Workspace — core algorithm reference

This documents the actual business logic behind the Business Workspace (`/w`) — the trader-facing app
(Sell, Stock, Money, Buy/Receive, Bills, Customers, Suppliers, Wastage). It is a reference to what is
implemented in `backend/app/modules/*` and `backend/app/core/*`, not a spec to build from scratch — each
section names the real source file. If the code and this doc ever disagree, the code is right; update this
file to match.

## Core principle: everything is a sum over an append-only ledger

Stock, money owed, and crates held are never stored as a mutable running total. Each is a table of signed
entries that is only ever inserted into (`backend/app/core/db.py` — append-only tables get a DB trigger via
`make_append_only` that revokes `UPDATE`/`DELETE`). The current balance is always `SUM(signed_amount)` over
that table, computed on read. A mistake is fixed with a new reversing entry, never an edit — so the full
history is always reconstructable and auditable.

This one idea underlies stock, the party (money) ledger, and the crate ledger below.

## 1. Bill / document numbering

`backend/app/core/numbering.py`

- Format: `<FY>/<series>/<6-digit seq>`, e.g. `26-27/S/000123` — at most 16 characters (GST requires
  invoice numbers to be unique, sequential, ≤16 chars).
- Financial year is Indian (April–March): `financial_year(2026, 9)` → `"26-27"`.
- One counter row per `(business_id, fy, series)`, created on first use via `INSERT ... ON CONFLICT DO
  NOTHING`, then locked with `SELECT ... FOR UPDATE` **inside the document's own transaction**:
  - if the document fails to save, the transaction rolls back and the number was never consumed (gap-free);
  - if two bills are created concurrently, the second blocks on the row lock until the first commits.
- Numbers are never reused, even when a bill is later voided.

## 2. GST pricing (pure functions, no DB)

`backend/app/modules/sales/pricing.py` — deliberately side-effect-free so it can be unit-tested against
fixed vectors on both the backend and the frontend (`frontend/src/lib/pricing.ts` mirrors it exactly).

All amounts are integer paise. No floats, no `Decimal`, anywhere.

1. **Line taxable value**: `unit_price_paise * quantity_base / base_factor`, rounded half-up to the paisa.
2. **Line tax**: GST rate is looked up per product (0/0.25/3/5/12/18/28%, in basis points). Prices are
   tax-exclusive, charged on top:
   - same state → split the rate equally into CGST + SGST, each rounded half-up on its own half-rate (so
     CGST always equals SGST);
   - different state → the whole rate as IGST.
   - A business with no GSTIN cannot charge GST at all (`gst_needs_gstin`); the bill becomes a **Bill of
     Supply** instead of a **Tax Invoice** when nothing on it is taxed.
3. **Bill total**: sum every line's taxable + tax, then round the *whole bill* half-up to the nearest rupee.
   The difference between the exact sum and the rounded total is shown as `round_off` — never hidden.

Interstate vs intrastate is decided by comparing the seller's GSTIN state code to the buyer's GSTIN state
code (or an explicit `place_of_supply` for a walk-in without one).

## 3. Making a sale (`Sell`) — the end-to-end orchestration

`backend/app/modules/sales/service.py::create_sale`, one DB transaction, all-or-nothing:

1. Check the `sell` module is enabled and the actor has `bills.create` (service layer, not just the router).
2. Resolve each line's product/variety/grade/unit against the catalog.
3. Decide tax invoice vs bill of supply, price every line (§2), sum to bill totals.
4. Reject a zero-or-negative bill (`zero_total`), reject payments that exceed the total (`overpaid`).
5. Whatever isn't paid becomes credit: if there's no customer, that's a hard error (`credit_needs_customer`);
   if the customer has a credit limit, going over it is a hard error (`credit_limit_exceeded`).
6. Pull the next bill number (§1) and insert the `Bill` + `BillLine` rows.
7. **Stock out**, one movement per line, in a fixed order — lines are sorted by `product_id` first so that
   two concurrent bills selling the same products always take their per-item locks in the same order and
   can never deadlock against each other (§4).
8. If there's a customer, post one `sale` entry to their party ledger for the full bill total (§5), then one
   `payment_in` entry per payment method actually collected (§6) — the ledger entry is for the total owed,
   the payment entries bring it back down by what was actually paid, leaving exactly the credit portion
   outstanding.
9. Write the audit event (before/after snapshot) in the same transaction.

Cancelling a bill (`void_bill`) is the mirror image: it does not delete anything, it posts the equal and
opposite stock and ledger entries and flips `status` to `void` (guarded by a DB trigger — `guard_void_only`
— so nothing else about a bill can ever be edited after creation).

## 4. Stock ledger

`backend/app/modules/inventory/service.py`

- `StockMovement` is append-only, keyed by `(location_id, product_id, variety_id, grade_id)`. Balance at any
  point is `SUM(quantity)` over matching rows — positive quantity is stock in, negative is stock out.
- Before any stock-out, a Postgres advisory transaction lock is taken on
  `hashtextextended("<business>:<location>:<product>", 0)` (`_lock_item`), then the running balance is
  re-read and checked: going negative raises `insufficient_stock`. The lock is released automatically when
  the transaction ends.
- Multi-line operations (a sale, a transfer) always process their lines **sorted by product id** before
  taking any locks — a fixed global order across every code path means two concurrent operations touching
  the same products can never deadlock waiting on each other.
- Movement types: `opening`, `adjustment`, `transfer_out`/`transfer_in`, `wastage`, `sale`, `sale_return`,
  `purchase`, `reversal`. A transfer is two linked movements (out of one location, into another) under one
  `StockTransfer` row. Only `opening`, `adjustment`, and `wastage` are directly reversible
  (`reverse_movement`) — reversing posts a new movement with the negated quantity, linked via
  `reversal_of`, and a movement can only be reversed once (`already_reversed`).

## 5. Party (money) ledger — who owes whom

`backend/app/modules/ledger/service.py::post_party_entry` / `party_balances`

- One signed integer paise amount per entry. Balance = `SUM(amount_paise)` for that party.
- Sign convention: **positive = the party owes the business more; negative = the party owes less** (or the
  business owes them). So:
  - a `sale` on credit posts **+total_paise** (they now owe more);
  - a `payment_in` (money received from them) posts **−amount_paise** (they now owe less);
  - a `payment_out` (money paid to them, e.g. a refund) posts **+amount_paise**.
- `entry_type` values: `opening`, `sale`, `sale_return`, `purchase`, `purchase_return`, `payment_in`,
  `payment_out`, `adjustment`, `reversal`. A manual `adjustment` is the escape hatch for correcting a
  mistake — always audited, never edits history.
- Party existence is enforced by a composite foreign key (`business_id`, `party_id`), not an application
  check, so an entry can never accidentally reference another tenant's party.

## 6. Crate ledger

`backend/app/modules/ledger/service.py` (`record_crates` / `crate_balances`)

Same append-only, sum-to-balance shape as the party ledger, but counting crates instead of money:
`issued` posts a positive quantity, `returned` posts a negative one, `adjustment` is the manual correction.
Balance per party = `SUM(quantity)`; `crate_balances(only_outstanding=True)` (the default) hides parties
sitting at exactly zero.

## 7. Payments

`backend/app/modules/ledger/service.py::record_payment`

A `Payment` row (method: cash/UPI/card/bank/cheque/other, direction: in/out) is created first; if it's tied
to a party and `post_to_ledger` is true, it also posts the corresponding party-ledger entry (§5) in the same
transaction. `reverse_payment` posts the equal-and-opposite payment (and ledger entry), linked via
`reversal_of` — same pattern as stock reversal, never an edit.

## 8. Idempotency — safe retries over flaky market wifi

`backend/app/core/idempotency.py::run_idempotent`

Every PWA write takes an `Idempotency-Key` header (client-generated once per user action, reused across
retries of *that* action). The key row is inserted **in the same transaction** as the business action:

- insert succeeds → the action runs, its response is stored on the same row, transaction commits together;
- insert fails on the unique `(business_id, user_id, key)` index (a retry, or a concurrent duplicate) →
  nothing new is written; the stored response is replayed byte-for-byte (`Idempotent-Replayed: true`
  header). If the same key shows up with a *different* request body, that's a hard error
  (`idempotency_reused`) rather than silently doing the wrong thing.
- If the action's own transaction rolls back (any error), the key row rolls back with it — so a genuinely
  failed request is safe to retry with the same key.

## 9. Tenant isolation and permissions (every algorithm above runs inside this)

`backend/app/core/db.py`, `backend/app/core/deps.py`, `backend/app/modules/accounts/service.py`

- Every tenant-owned table carries `business_id`; the current business comes only from the logged-in
  session's membership (`WorkspaceCtx`), never from anything the client sends. Three layers enforce it:
  ORM query filtering, a `before_flush` guard against cross-tenant writes, and Postgres row-level security
  as the final backstop (`SET LOCAL app.business_id`, `FORCE ROW LEVEL SECURITY`).
- Every service function checks `require_module` (is this section enabled for this business?) and
  `require_permission` (does this role have this permission?) itself — not just the router — plus
  `ctx.can_access_location` wherever a location is involved. A disabled module or missing permission is a
  403, not just a hidden UI element.

## Where this doc stops

This covers the shared transactional core. Vertical-specific behavior (which units/varieties a trade
suggests, its default modules, its illustrative workflow steps) is *configuration*, not algorithm — see
`vertical_templates` (`backend/app/modules/platform/models.py`) and the Admin Configuration page, not this
file.
