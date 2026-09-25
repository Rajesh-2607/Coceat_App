"""Per-request context passed from routers into services."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None
    request_id: str | None


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: uuid.UUID
    is_platform_admin: bool


@dataclass(frozen=True, slots=True)
class Tenant:
    business_id: uuid.UUID
    role: str
    location_ids: tuple[uuid.UUID, ...] | None  # None = all locations
    enabled_modules: frozenset[str]


@dataclass(frozen=True, slots=True)
class Ctx:
    """Workspace request: authenticated user acting inside their current business."""

    db: AsyncSession
    actor: Actor
    tenant: Tenant
    meta: RequestMeta

    def can_access_location(self, location_id: uuid.UUID) -> bool:
        return self.tenant.location_ids is None or location_id in self.tenant.location_ids


@dataclass(frozen=True, slots=True)
class PlatformCtx:
    """Admin request: platform staff, no current business."""

    db: AsyncSession
    actor: Actor
    meta: RequestMeta
