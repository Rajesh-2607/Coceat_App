import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.core.config import get_settings
from app.core.deps import AdminCtx, CurrentSession, Db, Meta, WorkspaceCtx
from app.core.security import SESSION_COOKIE
from app.modules.accounts import service
from app.modules.accounts.schemas import (
    MemberIn,
    MemberOut,
    MeOut,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    SelectBusinessIn,
)
from app.modules.accounts.sms import get_sms_sender
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


@router.post("/auth/otp/request", response_model=OtpRequestOut, status_code=status.HTTP_202_ACCEPTED)
async def request_otp(body: OtpRequestIn, db: Db, meta: Meta, background: BackgroundTasks) -> OtpRequestOut:
    issued = await service.request_otp(db, body.phone, meta)
    if issued.code_to_send is not None:
        # sent after the response so timing doesn't reveal whether the number is registered
        background.add_task(get_sms_sender().send_otp, issued.phone, issued.code_to_send)
    return OtpRequestOut(challenge_id=issued.challenge_id, expires_in_seconds=int(service.OTP_TTL.total_seconds()))


@router.post("/auth/otp/verify", response_model=MeOut)
async def verify_otp(body: OtpVerifyIn, db: Db, meta: Meta, response: Response) -> MeOut:
    token, expires_at = await service.verify_otp(db, body.challenge_id, body.code, meta)
    _set_session_cookie(response, token, expires_at)
    user_session, user = await service.authenticate(db, token)
    return await service.me(db, user_session, user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(db: Db, session: CurrentSession, meta: Meta, response: Response) -> None:
    await service.logout(db, session[0], meta)
    await db.commit()
    response.delete_cookie(SESSION_COOKIE, domain=get_settings().cookie_domain or None, path="/")


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
