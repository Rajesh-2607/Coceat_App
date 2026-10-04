import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from app.core.deps import WorkspaceCtx
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission, user_names
from app.modules.audit import service
from app.modules.platform.modules import ModuleKey

router = APIRouter(prefix="/w/audit-events", tags=["audit"])


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    actor_user_id: uuid.UUID | None
    actor_name: str | None = None
    action: str
    entity_type: str | None
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    next_before_seq: int | None


@router.get("", response_model=AuditPage)
async def list_audit_events(
    ctx: WorkspaceCtx,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    action: Annotated[str | None, Query(max_length=60)] = None,
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> AuditPage:
    require_module(ctx, ModuleKey.AUDIT)
    require_permission(ctx, Perm.AUDIT_VIEW)
    rows = await service.list_events(
        ctx,
        before_seq=before_seq,
        limit=limit,
        action=action,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
    )
    names = await user_names(ctx.db, {r.actor_user_id for r in rows if r.actor_user_id is not None})
    items = []
    for r in rows:
        item = AuditEventOut.model_validate(r)
        item.actor_name = names.get(r.actor_user_id) if r.actor_user_id else None
        items.append(item)
    return AuditPage(items=items, next_before_seq=items[-1].seq if len(items) == limit else None)
