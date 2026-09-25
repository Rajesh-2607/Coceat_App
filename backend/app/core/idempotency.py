"""Idempotent writes for the PWA (flaky market networks retry; a retried sale must never bill twice).

The key row is inserted in the SAME transaction as the business action:
- the action fails  -> the key row rolls back with it, so the client can safely retry;
- a concurrent duplicate blocks on the unique index until the first commits, then replays its response.
"""

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import ForeignKey, Index, SmallInteger, String, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column
from starlette.responses import JSONResponse

from app.core.context import Ctx
from app.core.db import Base, IdMixin, TenantMixin
from app.core.errors import Unprocessable
from app.core.ids import uuid7

REPLAY_HEADER = "Idempotent-Replayed"
KEY_PATTERN = r"^[A-Za-z0-9_-]{16,100}$"


class IdempotencyRecord(IdMixin, TenantMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("business_id", "user_id", "key"),
        Index("ix_idempotency_keys_created_at", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


def _request_hash(operation: str, payload: BaseModel | None) -> str:
    body = payload.model_dump(mode="json") if payload is not None else None
    raw = json.dumps([operation, body], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


async def run_idempotent(
    ctx: Ctx,
    key: str,
    operation: str,
    payload: BaseModel | None,
    action: Callable[[], Awaitable[BaseModel]],
    *,
    status_code: int = 200,
) -> JSONResponse:
    """Run ``action`` once per (business, user, key); commit; return (or replay) its response."""
    req_hash = _request_hash(operation, payload)
    inserted = await ctx.db.scalar(
        insert(IdempotencyRecord)
        .values(
            id=uuid7(),
            business_id=ctx.tenant.business_id,
            user_id=ctx.actor.user_id,
            key=key,
            request_hash=req_hash,
        )
        .on_conflict_do_nothing(index_elements=["business_id", "user_id", "key"])
        .returning(IdempotencyRecord.id)
    )

    if inserted is None:
        record = await ctx.db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == ctx.actor.user_id, IdempotencyRecord.key == key
            )
        )
        if record is None or record.response_status is None:  # pragma: no cover - defensive
            raise Unprocessable("Idempotency key state is inconsistent", code="idempotency_inconsistent")
        stored_hash, stored_status, stored_body = (
            record.request_hash,
            record.response_status,
            record.response_body,
        )
        await ctx.db.rollback()  # nothing was written; end the read transaction
        if stored_hash != req_hash:
            raise Unprocessable("Idempotency-Key was reused for a different request", code="idempotency_reused")
        return JSONResponse(stored_body, status_code=stored_status, headers={REPLAY_HEADER: "true"})

    result = await action()
    body = result.model_dump(mode="json")
    record = await ctx.db.get_one(IdempotencyRecord, inserted)
    record.response_status = status_code
    record.response_body = body
    await ctx.db.commit()
    return JSONResponse(body, status_code=status_code)
