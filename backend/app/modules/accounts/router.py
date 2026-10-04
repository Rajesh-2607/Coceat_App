import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.config import get_settings
from app.core.deps import AdminCtx, CurrentSession, Db, Meta, WorkspaceCtx
from app.core.security import SESSION_COOKIE
from app.modules.accounts import service
from app.modules.accounts.schemas import (
    LoginIn,
    MemberIn,
    MemberOut,
    MeOut,
    PasswordChangeIn,
    PlatformUserOut,
    PlatformUserUpdate,
    SelectBusinessIn,
    StaffOut,
    StaffUpdate,
)
from app.modules.platform import service as platform
from app.modules.platform.schemas import WorkspaceContextOut

router = APIRouter(tags=["accounts"])


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        expires=expires_at,
        httponly=True,
        secure=s.is_production_like,
        samesite="lax",
        domain=s.cookie_domain or None,
        path="/",
    )


@router.post("/auth/login", response_model=MeOut)
async def login(body: LoginIn, db: Db, meta: Meta, response: Response) -> MeOut:
    token, expires_at = await service.login(db, body.username, body.password, meta)
    _set_session_cookie(response, token, expires_at)
    user_session, user = await service.authenticate(db, token)
    return await service.me(db, user_session, user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(db: Db, session: CurrentSession, meta: Meta, response: Response) -> None:
    await service.logout(db, session[0], meta)
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, domain=get_settings().cookie_domain or None, path="/")


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChangeIn, db: Db, session: CurrentSession, meta: Meta) -> None:
    user_session, user = session
    await service.change_password(db, user_session, user, body, meta)
    await db.commit()


@router.get("/me", response_model=MeOut)
async def me(db: Db, session: CurrentSession) -> MeOut:
    return await service.me(db, *session)


@router.put("/me/business", response_model=MeOut)
async def select_business(body: SelectBusinessIn, db: Db, session: CurrentSession) -> MeOut:
    await service.select_business(db, session[0], body.business_id)
    await db.commit()
    return await service.me(db, *session)


@router.get("/w/context", response_model=WorkspaceContextOut)
async def workspace_context(ctx: WorkspaceCtx) -> WorkspaceContextOut:
    return WorkspaceContextOut(
        business=await platform.get_business(ctx.db, ctx.tenant.business_id),
        role=ctx.tenant.role,
        location_ids=list(ctx.tenant.location_ids) if ctx.tenant.location_ids is not None else None,
        permissions=service.permissions_of(ctx.tenant.role),
    )


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.put("/businesses/{business_id}/members", response_model=MemberOut)
async def upsert_member(business_id: uuid.UUID, body: MemberIn, ctx: AdminCtx) -> MemberOut:
    out = await service.add_member(ctx, business_id, body)
    await ctx.db.commit()
    return out


@admin_router.get("/businesses/{business_id}/members", response_model=list[StaffOut])
async def list_members(business_id: uuid.UUID, ctx: AdminCtx) -> list[StaffOut]:
    await platform.get_business(ctx.db, business_id)  # 404 if missing
    return await service.list_staff(ctx.db, business_id)


@admin_router.patch("/businesses/{business_id}/members/{membership_id}", response_model=StaffOut)
async def update_member(business_id: uuid.UUID, membership_id: uuid.UUID, body: StaffUpdate, ctx: AdminCtx) -> StaffOut:
    out = await service.admin_update_staff(ctx, business_id, membership_id, body)
    await ctx.db.commit()
    return out


@admin_router.get("/users", response_model=list[PlatformUserOut])
async def list_platform_users(
    ctx: AdminCtx, q: Annotated[str | None, Query(max_length=60)] = None
) -> list[PlatformUserOut]:
    return await service.list_platform_users(ctx, q=q)


@admin_router.patch("/users/{user_id}", response_model=PlatformUserOut)
async def update_platform_user(user_id: uuid.UUID, body: PlatformUserUpdate, ctx: AdminCtx) -> PlatformUserOut:
    out = await service.update_platform_user(ctx, user_id, body)
    await ctx.db.commit()
    return out
