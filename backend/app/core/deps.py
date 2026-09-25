"""FastAPI dependencies. The current business comes ONLY from the session's validated membership."""

from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.context import Ctx, PlatformCtx, RequestMeta
from app.core.db import get_db, set_tenant
from app.core.errors import Forbidden, Unauthorized
from app.core.idempotency import KEY_PATTERN
from app.core.security import SESSION_COOKIE
from app.modules.accounts import service as accounts
from app.modules.accounts.models import User, UserSession

Db = Annotated[AsyncSession, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    hops = get_settings().trusted_proxy_hops
    if hops:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops][:45]
    return request.client.host if request.client else None


def request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


Meta = Annotated[RequestMeta, Depends(request_meta)]


async def current_session(
    db: Db, cc_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None
) -> tuple[UserSession, User]:
    return await accounts.authenticate(db, cc_session)


CurrentSession = Annotated[tuple[UserSession, User], Depends(current_session)]


async def get_current_business(db: Db, session: CurrentSession, meta: Meta) -> Ctx:
    user_session, user = session
    tenant = await accounts.resolve_tenant(db, user.id, user_session.business_id)
    if tenant is None:
        raise Unauthorized("Choose a business first", code="no_current_business")
    await set_tenant(db, tenant.business_id)
    return Ctx(db=db, actor=accounts.actor_of(user), tenant=tenant, meta=meta)


WorkspaceCtx = Annotated[Ctx, Depends(get_current_business)]


async def get_platform_admin(db: Db, session: CurrentSession, meta: Meta) -> PlatformCtx:
    _, user = session
    if not user.is_platform_admin:
        raise Forbidden()
    return PlatformCtx(db=db, actor=accounts.actor_of(user), meta=meta)


AdminCtx = Annotated[PlatformCtx, Depends(get_platform_admin)]

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", pattern=KEY_PATTERN)]
