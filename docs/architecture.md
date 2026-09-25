# Cocreat architecture

Status: foundation implemented (tenancy, auth, audit, idempotency, locations, deploy pipeline).
Sales, stock movements, ledgers and PDFs are built on top of this and follow the same patterns.

## 1. Topology

```
 Trader's Android phone (PWA, Tamil/English)
        │ HTTPS
        ▼
 Cloudflare Pages ── app.cocreat.in ── static app shell, CDN-cached, free tier
        │ fetch (credentials: include, httpOnly cookie)
        ▼
 Render web service ── api.cocreat.in ── Docker, FastAPI + uvicorn, region Singapore
        │  pooled connection (PgBouncer, transaction mode), role cocreat_app (RLS applies)
        ▼
 Neon Postgres 16 ── AWS ap-southeast-1 (Singapore) ── autoscaling, PITR
        ▲
        │ direct connection, owner role: Alembic migrations only (Render pre-deploy)
        │
 GitHub Actions ── CI on every PR · nightly cleanup · nightly encrypted pg_dump ──▶ Cloudflare R2
 Sentry ── errors, scrubbed of cookies, headers, bodies and query strings
```

**Why Singapore for both API and DB.** Each request makes several DB round-trips, and each extra
millisecond between API and DB is paid on every one of them. Put the API next to the database.
Chennai to Singapore adds about 35–45 ms, and a phone pays that once per request. Render has no
Indian region. If Neon and Render both offer Mumbai later, move them together.

## 2. Request path and tenant isolation

Tenant isolation has four independent layers. All of them fail closed.

| Layer | Where | What it does |
| --- | --- | --- |
| Membership | `core/deps.py::get_current_business` | The business comes only from the session's validated, active membership. The client can pick among its own memberships (`PUT /api/me/business`), never set a business ID on a request |
| ORM filter | `core/db.py` `do_orm_execute` | Adds `business_id = <current>` to every SELECT/UPDATE/DELETE on a `TenantMixin` model |
| Flush guard | `core/db.py` `before_flush` | Stamps new rows with the current business; raises on cross-tenant writes or when no business is set |
| Postgres RLS | migration `0001` | `FORCE`d policies against `app_current_business()`, set per transaction with `set_config(..., true)`. That is transaction-local, so it's safe with Neon's transaction pooler |

The API connects as `cocreat_app`, a non-owner role. Superusers bypass RLS, so the tests
reproduce Neon's role layout exactly: a non-superuser owner runs migrations and the app role
runs the API. `tests/test_migrations.py` fails the build if a tenant table ships without forced RLS.

## 3. Write path: one transaction per business action

```
router ──▶ run_idempotent(key) ──▶ service (checks permission, module, location) ──▶ flush rows + audit event
              │ INSERT idempotency key ─┐                                                   │
              └─────────────── same transaction; ONE commit ◀──────────────────────────────┘
```

- **Services never commit.** The router commits once, through `run_idempotent` or `db.commit()`.
  The one exception is auth, because OTP attempt counters must persist even when the request fails.
- **Idempotency.** The key row lives in the same transaction as the action. If the action fails,
  the key rolls back and the client can retry. A concurrent duplicate blocks on the unique index,
  then replays the stored response (tested with 5 parallel requests). Reusing a key with a
  different body returns 422. The frontend creates one key per user action, so automatic retries
  reuse it.
- **Audit.** `audit_events` gets rows in the same transaction. The app role has no UPDATE, DELETE
  or TRUNCATE privilege and there is no RLS policy for those operations. A trigger rejects them
  even for roles that bypass RLS.

## 4. Security model

| Threat | Control |
| --- | --- |
| Session theft via XSS | Opaque random token in an `HttpOnly; Secure; SameSite=Lax` cookie. The DB stores only its HMAC. Strict CSP on Pages |
| CSRF | SameSite=Lax, plus the API rejects cookie-authenticated unsafe requests whose `Origin` isn't allow-listed |
| Stolen or lost phone | Server-side sessions: revocation takes effect immediately (logout tested). 30-day expiry |
| OTP brute force | 6 digits, 5-minute TTL, 5 attempts per challenge, single use, HMAC-stored, constant-time compare |
| SMS pumping (cost attack) | SMS is sent only to registered users. Unknown numbers get an identical response but no SMS. Limits: 3 per phone per 10 min, 20 per IP per hour |
| Phone enumeration | Identical response and timing: SMS is sent in a background task after the response |
| IP spoofing via `X-Forwarded-For` | Client IP is taken `TRUSTED_PROXY_HOPS` from the right, never the leftmost entry |
| Secrets leakage | `SecretStr`; `config.py` is the only env reader; logs contain path only (no query, headers or cookies); Sentry scrubbed; `/docs` and `/openapi.json` are off in production |
| Unsafe production configuration | Startup refuses `OTP_DEV_MODE`, a short `SESSION_SECRET` or `http://` CORS origins when `APP_ENV=production` |
| Container compromise | Non-root user, slim image with no compilers |

## 5. Scalability plan

The current design needs no Redis, no queue and no Kubernetes. Each step below is triggered by
a measurement, not a guess.

| Stage | Trigger | Change |
| --- | --- | --- |
| 0 (launch) | – | Render Starter, 2 workers; Neon autoscaling from 0.25 CU |
| 1 | p95 latency above 300 ms or CPU above 70% sustained | Render Standard (vertical); `WEB_CONCURRENCY=4` |
| 2 | One instance saturated | `numInstances: 2+`. The app is stateless (sessions live in Postgres), so this needs no code change |
| 3 | Reports slow down billing | Point `reports` queries at a Neon read replica (a second engine) |
| 4 | PDF or WhatsApp volume | Move `BackgroundTasks` work to a Render background worker with a Postgres-backed job table (`SELECT … FOR UPDATE SKIP LOCKED`). Still no Redis |

Connection budget: each worker opens at most `DB_POOL_SIZE + DB_MAX_OVERFLOW` (5 + 5)
connections to Neon's pooler, which accepts up to 10,000 client connections.

## 6. Cost (estimates; verify current pricing before committing)

| Item | Launch | ~200 businesses |
| --- | --- | --- |
| Render web service | Starter ≈ $7/mo | Standard ≈ $25/mo (× instances) |
| Neon | Launch plan, usage-based ≈ $5–20/mo | ≈ $20–70/mo |
| Cloudflare Pages + R2 | Free (R2: 10 GB free, zero egress) | Low single-digit $ |
| GitHub Actions | Free tier (private repo minutes) | Free tier |
| Sentry | Free tier | Team plan if needed |
| SMS OTP (DLT) | ≈ ₹0.15–0.25 per SMS | Bounded by registered users × rate limit |

Cost controls built in: scale-to-zero on the staging DB, no always-on queue or cache, a
CDN-served frontend, no egress fees on R2, and 30-day sessions that keep OTP SMS volume low.

## 7. Reliability

- **Deploys.** CI must pass (`autoDeployTrigger: checksPass`). Render runs `alembic upgrade head`
  as the pre-deploy step, so a failed migration aborts the deploy before any traffic moves. Old
  instances drain gracefully (`--timeout-graceful-shutdown 20`).
- **Migrations.** Backward-compatible only (add first, remove in a later release), so the old and
  new versions can run side by side during a deploy. `lock_timeout=10s` stops a migration from
  queueing behind live traffic.
- **Backups.** Two independent copies: Neon point-in-time restore (primary), plus a nightly
  `pg_dump` encrypted with `age` and uploaded to R2 (secondary). The decryption key is kept
  offline. **Run a restore drill before go-live and quarterly after that.**
- **Health checks.** `/healthz` for liveness (no DB, so Neon's cold start can't cause restarts)
  and `/readyz` for monitors.
- **Retention.** The nightly job deletes only technical rows: idempotency keys (7 days), OTPs
  (2 days) and expired sessions. Ledgers and audit events are never deleted.

## 8. Decisions that still need you

1. **Bill number format** (series, prefix, FY reset) and **rounding rules** (paise per line vs per
   bill, GST rounding, round-off to the rupee). These are legally sensitive and block the sales module.
2. **SMS provider.** `Msg91SmsSender` follows MSG91's v5 flow API. Verify it against your account
   and your DLT template before go-live.
3. **Domains.** Config assumes `app.cocreat.in` and `api.cocreat.in`. Change `CORS_ORIGINS`,
   `render.yaml` and `frontend/public/_headers` if the domains differ.
4. **SQLAdmin was not added.** It writes around the service layer, which would skip audit events
   and permission checks. Platform admin is the React `/admin` app on audited admin endpoints.
   Add SQLAdmin later only as read-only if the team wants it.
5. **Backup role.** `pg_dump` needs a role with `BYPASSRLS`. Confirm that Neon lets you create one
   (see deployment.md). If it doesn't, rely on Neon PITR plus Neon branch snapshots.
