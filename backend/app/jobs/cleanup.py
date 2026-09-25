"""Nightly retention job (GitHub Actions): `python -m app.jobs.cleanup`.

Deletes only expendable technical rows. Ledgers and audit events are never touched.
Runs as the app role, one business at a time, so RLS stays on even for maintenance.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker, set_tenant
from app.core.idempotency import IdempotencyRecord
from app.core.logging import configure_logging
from app.modules.accounts.models import OtpChallenge, UserSession
from app.modules.platform.models import Business

log = logging.getLogger("app.jobs.cleanup")

IDEMPOTENCY_RETENTION = timedelta(days=7)  # far longer than any PWA retry window
OTP_RETENTION = timedelta(days=2)
SESSION_RETENTION = timedelta(days=30)  # after expiry/revocation


async def run() -> dict[str, int]:
    now = datetime.now(UTC)
    counts = {"idempotency_keys": 0}
    async with get_sessionmaker()() as db:
        result = await db.execute(delete(OtpChallenge).where(OtpChallenge.created_at < now - OTP_RETENTION))
        counts["otp_challenges"] = result.rowcount  # type: ignore[attr-defined]
        result = await db.execute(delete(UserSession).where(UserSession.expires_at < now - SESSION_RETENTION))
        counts["user_sessions"] = result.rowcount  # type: ignore[attr-defined]
        await db.commit()

        business_ids = list(await db.scalars(select(Business.id)))
        for business_id in business_ids:
            await set_tenant(db, business_id)
            result = await db.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.created_at < now - IDEMPOTENCY_RETENTION)
            )
            counts["idempotency_keys"] += result.rowcount  # type: ignore[attr-defined]
            await db.commit()
    await get_engine().dispose()
    return counts


def main() -> None:
    configure_logging(get_settings().log_level)
    log.info("cleanup.done", extra=asyncio.run(run()))


if __name__ == "__main__":
    main()
