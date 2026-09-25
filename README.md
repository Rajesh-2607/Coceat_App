# Cocreat Business OS

Multi-tenant SaaS for wholesale traders in Chennai markets (Koyambedu, Madhavaram): banana, vegetable, flower
and tomato wholesalers. One platform, many businesses. Each business gets its own configured workspace.

- **Cocreat Admin** (`/admin`): the platform team manages businesses, users and vertical configuration.
- **Business Workspace** (`/w`): traders handle sales, stock, money, bills, customers and more, in Tamil or English,
  as an installable PWA on the phones they already use.

> Status: the foundation is in place (tenancy, OTP login, audit trail, idempotent writes, locations,
> deployment pipeline). Sales, stock movements, ledgers and PDF bills come next.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 16 on Neon, with row-level security |
| Frontend | React 18, TypeScript, Vite, Tailwind, TanStack Query, react-i18next, PWA |
| API client | Generated from the backend's OpenAPI schema (`npm run gen:api`) |
| Hosting | Render (API), Cloudflare Pages (frontend), Neon (DB), Cloudflare R2 (files, backups) |
| CI / jobs | GitHub Actions |

## Repository layout

```
backend/     FastAPI app, Alembic migrations, tests
frontend/    React PWA (workspace + admin)
docs/        architecture.md (design, security, scaling, cost) and deployment.md (runbook)
render.yaml  Render blueprint for the API
.github/     CI and nightly (cleanup + encrypted backup) workflows
```

## Getting started

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22+
- A PostgreSQL 16 database for running the app locally (a free Neon branch works). The tests don't need one:
  they start an embedded Postgres automatically.

### Backend

```bash
cd backend
cp .env.example .env            # then fill in your own values; never commit .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload   # http://localhost:8000, API docs at /docs
```

With `OTP_DEV_MODE=true` (local only) no SMS is sent and the OTP is always `123456`. Create your first user
directly in the database; the SQL is in [docs/deployment.md](docs/deployment.md#6-first-platform-admin).

On Windows, keep `--reload`: psycopg's async mode needs the selector event loop, which uvicorn only uses in reload mode.

### Frontend

```bash
cd frontend
cp .env.example .env            # VITE_API_URL=http://localhost:8000
npm install
npm run dev                     # http://localhost:5173
```

## Checks

Run these before opening a pull request. CI runs the same ones.

```bash
# backend/
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest

# frontend/
npm run lint && npm run typecheck && npm run test && npm run build
npm run gen:api                 # after any API change; commit src/api/schema.d.ts
```

## Core rules

These are enforced in code and tests. [CLAUDE.md](CLAUDE.md) has the full list.

- **Tenant isolation:** the current business comes only from the logged-in user's membership, never from the request.
  Every tenant table has a `FORCE`d RLS policy, and the tests prove Business A gets 404 for Business B's data.
- **Money** is stored as integer paise and **weights** as integer grams.
- **Ledgers and audit events are append-only**; mistakes are fixed with reversing entries.
- **One transaction per business action**: bill, lines, stock, ledger and audit event succeed or fail together.
- **Idempotent writes**: every PWA write sends an `Idempotency-Key`, so retries on a bad network never duplicate a sale.
- **Secrets** come only from environment variables via `backend/app/core/config.py`. Never commit `.env` files.

## Deployment

See [docs/deployment.md](docs/deployment.md) for the step-by-step setup of Neon, Render, Cloudflare Pages, R2 and
GitHub secrets, and [docs/architecture.md](docs/architecture.md) for the design, security model, scaling plan and
cost estimates.
