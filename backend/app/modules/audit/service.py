"""'Who did what'. Every create, update, cancel, login and support access writes one event."""

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import Ctx, RequestMeta
from app.core.ids import uuid7
from app.modules.audit.models import AuditEvent


def snapshot(obj: BaseModel | None) -> dict[str, Any] | None:
    return obj.model_dump(mode="json") if obj is not None else None


async def record_event(
    db: AsyncSession,
    *,
    meta: RequestMeta,
    action: str,
    actor_user_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the caller's transaction (it commits or rolls back with the action).

    The table has implicit_returning off: Postgres checks RETURNING rows against the SELECT policy, and
    platform events (business_id NULL) are deliberately unreadable by the app role.
    """
    db.add(
        AuditEvent(
            id=uuid7(),
            business_id=business_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            before=before,
            after=after,
            ip=meta.ip,
            user_agent=(meta.user_agent or "")[:300] or None,
            request_id=meta.request_id,
        )
    )


async def record(
    ctx: Ctx,
    action: str,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    before: BaseModel | None = None,
    after: BaseModel | None = None,
) -> None:
    await record_event(
        ctx.db,
        meta=ctx.meta,
        action=action,
        actor_user_id=ctx.actor.user_id,
        business_id=ctx.tenant.business_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before=snapshot(before),
        after=snapshot(after),
    )


async def list_events(ctx: Ctx, *, before_seq: int | None, limit: int) -> list[AuditEvent]:
    """Newest first, keyset-paginated by ``seq`` (cheap at any depth, unlike OFFSET)."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.business_id == ctx.tenant.business_id)
        .order_by(AuditEvent.seq.desc())
        .limit(limit)
    )
    if before_seq is not None:
        stmt = stmt.where(AuditEvent.seq < before_seq)
    return list(await ctx.db.scalars(stmt))
