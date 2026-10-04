# syntax=docker/dockerfile:1.7
# Single-origin image for free hosting: the API serves the built web app from the same address, so the login
# cookie works without a custom domain. Build context is the repository root.
# (backend/Dockerfile is still used by CI and stays API-only.)

# ---- web: build the frontend ----
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty = same origin as the API (the app calls /api/... on its own host)
ARG VITE_API_URL=""
RUN VITE_API_URL="$VITE_API_URL" npm run build

# ---- build: resolve locked Python deps into /app/.venv ----
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY backend/ ./

# ---- runtime: no compilers, no uv, non-root ----
FROM python:3.12-slim-bookworm
# WeasyPrint (PDF bills) needs Pango; fonts-noto-core has Noto Sans Tamil for Tamil bills
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fontconfig fonts-noto-core \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
COPY --from=web --chown=app:app /web/dist /app/static
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FRONTEND_DIR=/app/static
USER app
EXPOSE 8000
# No --proxy-headers: client IPs are resolved from X-Forwarded-For with TRUSTED_PROXY_HOPS (spoof-safe).
# Free hosting has no pre-deploy step, so migrations run here, once per start (a single instance is assumed).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --no-server-header --timeout-graceful-shutdown 20"]
