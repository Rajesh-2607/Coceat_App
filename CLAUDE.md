# CLAUDE.md — Cocreat Business OS

This is a **real-world production project**, not a demo. It handles real traders' bills, stock and money.
Correctness, tenant isolation and auditability matter more than speed or cleverness. When unsure, ask before changing
anything that touches money, stock, bill numbering, auth or tenancy.

## What we're building

Cocreat is a multi-tenant SaaS "Business OS" for wholesale traders in Chennai markets (Koyambedu, Madhavaram):
banana, vegetable, flower and tomato wholesalers. One platform, many businesses. Each business gets its own
configured workspace.

Two apps, one frontend codebase:

- **Cocreat Admin** (`/admin`), for the platform team: businesses, subscriptions, users, vertical configuration, setup queue.
- **Business Workspace** (`/w`), for each trader: Home, Sell, Stock, Money, Buy/Receive, Bills, Customers, Suppliers,
  Wastage, Reports, Staff, Who did what, Settings. It has a location switcher, role-based access and Tamil/English.

v1 scope: billing with GST-compliant bills (Tax Invoice or Bill of Supply), stock by location, crates/units, credit
ledgers. Out of v1: buyer portal, full offline mode, WhatsApp API, online payment collection.

## Stack notes

- Internal admin is React `/admin` on audited `/api/admin` endpoints. SQLAdmin is not used: it bypasses services and audit.
- The API client in `frontend/src/api/` is generated from FastAPI's OpenAPI schema (`npm run gen:api`); never hand-write or edit it.
- Each backend module under `app/modules/` has `models.py`, `schemas.py`, `service.py`, `router.py`.

Run the tests, lint and type checks before saying a task is done.

## Environment variables and secrets (.env)

### How it works

- All configuration and secrets come from environment variables. In local development they are loaded from a
  `.env` file. In production they are set in the host's dashboard (Render, Cloudflare Pages, GitHub Actions secrets),
  and there is **no `.env` file** on those servers.
- `backend/app/core/config.py` defines a single `Settings` class using `pydantic-settings`. **This is the only place
  that reads environment variables.** All other code calls `get_settings()` from there. Never call `os.environ` or
  `os.getenv` elsewhere.
- Secret fields use `SecretStr` so they don't appear in logs, tracebacks or `repr()`. Read them with
  `.get_secret_value()` only at the point of use.
- The app must fail fast at startup if a required variable is missing. Don't give secrets default values.

The real class is `backend/app/core/config.py` (read it rather than trusting a copy here). Key points:
`get_settings()` is cached and is the only accessor; a validator refuses `OTP_DEV_MODE`, a short
`SESSION_SECRET` and `http://` CORS origins when `APP_ENV=production`.

The `.env.example` files are the source of truth for variable names and placeholder values; keep `backend/.env.example` in sync with `Settings`. Real `.env` files are never committed.

### Rules for Claude

1. **Never read, open, print, `cat`, grep or echo `.env` files or their values.** To learn which variables exist,
   read `.env.example` or `config.py`.
2. **Never write real secrets into any file**: code, tests, docs, commit messages, logs or `.env.example`.
   Use obvious placeholders (`change-me`, `your-api-key`).
3. When adding a new setting: add it to `Settings` in `config.py`, add a placeholder line with a comment to the
   matching `.env.example`, and tell the user which real value to add to their `.env` and to the hosting dashboard.
4. Never put secrets in `VITE_*` variables or anywhere in the frontend. Anything the browser needs that is secret
   must go through the backend.
5. Never log settings objects, request headers, cookies, OTPs or session tokens. Sentry must scrub them.
6. Tests use their own values via `monkeypatch` or a `tests/.env.test` with fake values. Tests never call real
   SMS, R2 or production databases.
7. `OTP_DEV_MODE` must be refused at startup when `APP_ENV=production`.
8. If a secret is ever committed or shown in output, stop and tell the user to rotate it. Deleting the file is not enough.

## Non-negotiable domain rules

- **Multi-tenancy:** every tenant table has `business_id`. The current business comes only from the logged-in user's
  membership, via the `get_current_business` dependency, never from a request body, query param or URL the client
  controls. Tenant models inherit `TenantMixin`; the session event filters queries automatically; Postgres RLS
  (`SET LOCAL app.business_id`) is the final backstop. Every new endpoint needs a test proving Business A gets 404
  for Business B's IDs.
- **Money** is stored as integer **paise** (`BIGINT`), never floats or `Decimal` in the DB. **Weights** are integer **grams**.
  Convert only at the API/UI edge.
- **Ledgers are append-only.** Stock movements, party ledger entries, crate ledger entries and audit events are never
  updated or deleted. Fix mistakes with reversing entries. Cancelled bills are marked void with a reason.
- **One transaction per business action.** A sale writes the bill, lines, stock movements, ledger entry and audit event
  in a single DB transaction. All succeed or none do.
- **Bill numbers** come from `bill_sequence` with `SELECT … FOR UPDATE` inside the bill's transaction. They are gap-free,
  sequential per financial year and series, and at most 16 characters.
- **Idempotency:** every write endpoint called from the PWA accepts an `Idempotency-Key` header. A repeated key returns
  the original result and never creates a duplicate.
- **Audit:** every create, update, cancel, login and support access writes an `audit_event` (who, what, before/after,
  device, time).
- **Modules are config-driven.** A disabled module must be refused by the API (403), not just hidden in the UI.
  New verticals are configuration, not new code; don't hard-code "banana" or "tomato" logic.
- **Permissions:** check role + allowed locations in the service layer, not only in routers.
- **GST:** support both Tax Invoice and Bill of Supply; GSTIN is optional per business. Don't change bill formats or
  numbering without asking; these are legally sensitive.

## Code conventions

- Modules talk to each other through `service.py` functions, never by importing another module's models to query directly.
- Routers are thin: validate with Pydantic schemas, call a service, return a schema.
- Async FastAPI endpoints with SQLAlchemy async sessions. No blocking I/O in request handlers; PDF generation runs
  in `BackgroundTasks`.
- Alembic migrations must be backward-compatible (add first, remove in a later release). Never edit a migration that
  has been applied to staging or production.
- Every user-facing string goes through i18n (`en.json` + `ta.json`). Product and party names have Tamil fields.
- The frontend never calls `fetch` directly; use the generated client via TanStack Query hooks.
- Keep UI touch targets large and flows short. Staff use cheap Android phones in a busy market.
- **Services never commit; the router commits once** (via `run_idempotent` for PWA writes, else `db.commit()`).
  Only auth flows commit inside the service (attempt counters must survive a failed request).
- Workspace endpoints take `ctx: WorkspaceCtx`; writes also take `key: IdempotencyKey` and go through
  `core.idempotency.run_idempotent`. Services call `require_module`, `require_permission`, check
  `ctx.can_access_location`, and write `audit.record(...)` in the same transaction.
- New tenant table: inherit `TenantMixin` and call `enable_tenant_rls("<table>")` in its migration (copy the helper
  from `0001`). `tests/test_migrations.py` fails if RLS is missing or models drift from migrations.
- Append-only tables (ledgers, audit): add `make_append_only` in the migration.
- Architecture and deployment: `docs/architecture.md`, `docs/deployment.md`.
- Windows dev: run uvicorn with `--reload` (psycopg async needs the selector event loop). Tests handle this.

## Before you finish a task

- [ ] Tests added or updated, including a tenant-isolation test for new endpoints
- [ ] `pytest`, `ruff`, `mypy`, frontend lint and typecheck all pass
- [ ] New settings added to `config.py` and `.env.example` (placeholders only)
- [ ] No secrets, real phone numbers or customer data in code, fixtures or logs
- [ ] Migration included if models changed
- [ ] Summary tells the user about any new env vars they must set locally and in Render / Cloudflare / GitHub
