# Deployment runbook

Do these steps once per environment: staging first, then production. Real values go in the host
dashboards only, never in git.

## 1. Neon (database)

1. Create a project in region **AWS Singapore (ap-southeast-1)**, Postgres 16, database `cocreat`.
   For staging, use a Neon **branch** of production, or a separate small project with scale-to-zero.
2. Copy both connection strings for the owner role:
   the **direct** one (host without `-pooler`) becomes `DATABASE_URL_DIRECT`.
   Change the scheme to `postgresql+psycopg://`.
3. Run the first migration from your machine (it creates the `cocreat_app` role as NOLOGIN):
   ```bash
   cd backend && DATABASE_URL_DIRECT=... uv run alembic upgrade head   # or put it in your local .env
   ```
4. In the Neon SQL editor, enable the app role. Generate the password with a password manager.
   ```sql
   ALTER ROLE cocreat_app LOGIN PASSWORD '<generated>';
   ALTER ROLE cocreat_app SET statement_timeout = '15s';
   ALTER ROLE cocreat_app SET idle_in_transaction_session_timeout = '30s';
   ```
   `DATABASE_URL` = the **pooled** host (`-pooler`) with user `cocreat_app`, `?sslmode=require`.
5. Optional backup role for the nightly dump:
   ```sql
   CREATE ROLE cocreat_backup LOGIN PASSWORD '<generated>' BYPASSRLS;
   GRANT pg_read_all_data TO cocreat_backup;
   ```
   If Neon refuses `BYPASSRLS`, skip the `backup` job and rely on Neon PITR (see architecture.md §8).
6. Set PITR retention to at least 7 days in production.

## 2. Render (API)

1. New → Blueprint → select this repo. It reads `render.yaml`.
2. Enter every `sync: false` value when prompted: `SESSION_SECRET`
   (`python -c "import secrets; print(secrets.token_urlsafe(64))"`), `DATABASE_URL`,
   `DATABASE_URL_DIRECT`, the SMS values, the R2 values and `SENTRY_DSN`.
3. Add a custom domain `api.cocreat.in` (a CNAME at your DNS provider).
4. Verify `TRUSTED_PROXY_HOPS=1` on staging: log in, then check that the new `auth.login` row
   in `audit_events` shows your real public IP. Adjust the value if it doesn't.
5. The first deploy runs `alembic upgrade head` automatically as the pre-deploy step.

## 3. Cloudflare Pages (frontend)

- Connect the repo. **Root directory:** `frontend`. **Build command:** `npm ci && npm run build`.
  **Output:** `dist`.
- Environment variable: `VITE_API_URL=https://api.cocreat.in`. This is public; never put a secret in a `VITE_` variable.
- Custom domain `app.cocreat.in`. `public/_headers` carries the CSP; update its `connect-src`
  if the API domain changes.

## 4. Cloudflare R2

- Bucket `cocreat-files` (bill PDFs) with an API token scoped to that bucket only → `R2_*` values.
- Bucket `cocreat-backups` with a separate token that can only write objects there. Add a
  lifecycle rule to delete objects after 35 days.

## 5. GitHub

- Create an Environment named `production` (require approval for manual runs if you want).
- **Secrets:** `SESSION_SECRET`, `DATABASE_URL`, `DATABASE_URL_DIRECT`, `SMS_API_KEY`,
  `SMS_SENDER_ID`, `SMS_OTP_TEMPLATE_ID`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `BACKUP_DATABASE_URL`, `R2_BACKUP_ACCESS_KEY_ID`,
  `R2_BACKUP_SECRET_ACCESS_KEY`.
- **Variables:** `BACKUP_AGE_RECIPIENT` (from `age-keygen`; the public key only), `R2_BACKUP_BUCKET`.
  Store the `age` private key offline (a password manager plus a printed copy). Without it the
  backups can't be read.
- Protect `main`: require the CI checks to pass before merging.

## 6. First platform admin

Users are platform rows (not RLS-protected). Create the first admin in the Neon SQL editor with
your own number:
```sql
INSERT INTO users (id, phone, name, language, is_platform_admin, is_active)
VALUES (gen_random_uuid(), '+91XXXXXXXXXX', 'Your name', 'en', true, true);
```
Everything after that goes through the audited `/api/admin` endpoints.

## 7. Restore drill (before go-live, then quarterly)

1. Download the latest `daily/*.dump.age` from R2 and decrypt it:
   `age -d -i key.txt file.dump.age > db.dump`.
2. Restore into a fresh Neon branch: `pg_restore --no-owner -d <branch-direct-url> db.dump`.
3. Point a local API at the branch and spot-check a few businesses' data.
4. Also rehearse a Neon PITR restore to a timestamp.

## Local development on Windows

psycopg's async mode cannot use Windows' default Proactor event loop. Run the dev server with
`--reload` (uvicorn then uses the selector loop):
`uv run uvicorn app.main:app --reload`. Tests handle this automatically. Production runs on Linux
and is unaffected.
