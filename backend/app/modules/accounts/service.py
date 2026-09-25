"""OTP login, sessions, memberships and permission checks.

Auth flows commit themselves: failure state (OTP attempt counters) must persist even when the request fails.
Everything else follows the normal rule: services never commit, the router commits once.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.context import Actor, Ctx, PlatformCtx, RequestMeta, Tenant
from app.core.db import set_tenant
from app.core.errors import Forbidden, TooManyRequests, Unauthorized, Unprocessable
from app.core.security import (
    hash_ip,
    hash_otp,
    hash_session_token,
    new_otp,
    new_session_token,
    normalize_indian_mobile,
    otp_matches,
)
from app.modules.accounts.models import Membership, OtpChallenge, User, UserSession
from app.modules.accounts.permissions import Perm, Role, role_has
from app.modules.accounts.schemas import MemberIn, MemberOut, MembershipOut, MeOut
from app.modules.audit import service as audit
from app.modules.platform import service as platform
from app.modules.platform.modules import ModuleKey

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
OTP_PER_PHONE = (3, timedelta(minutes=10))
OTP_PER_IP = (20, timedelta(hours=1))


def _now() -> datetime:
    return datetime.now(UTC)


def _phone_or_422(raw: str) -> str:
    phone = normalize_indian_mobile(raw)
    if phone is None:
        raise Unprocessable("Enter a valid 10-digit mobile number", code="invalid_phone")
    return phone


# --- OTP login -------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OtpIssued:
    challenge_id: uuid.UUID
    phone: str
    code_to_send: str | None  # None when no active user has this phone (response stays identical)


async def request_otp(db: AsyncSession, raw_phone: str, meta: RequestMeta) -> OtpIssued:
    phone = _phone_or_422(raw_phone)
    now = _now()
    ip_hash = hash_ip(meta.ip)

    limit, window = OTP_PER_PHONE
    recent = await db.scalar(
        select(func.count())
        .select_from(OtpChallenge)
        .where(OtpChallenge.phone == phone, OtpChallenge.created_at > now - window)
    )
    if (recent or 0) >= limit:
        raise TooManyRequests("Too many OTP requests. Try again in a few minutes.", code="otp_rate_limited")
    if ip_hash:
        limit, window = OTP_PER_IP
        recent = await db.scalar(
            select(func.count())
            .select_from(OtpChallenge)
            .where(OtpChallenge.ip_hash == ip_hash, OtpChallenge.created_at > now - window)
        )
        if (recent or 0) >= limit:
            raise TooManyRequests("Too many OTP requests. Try again later.", code="otp_rate_limited")

    user_exists = await db.scalar(select(User.id).where(User.phone == phone, User.is_active.is_(True)))
    challenge_id = uuid.uuid4()
    code = new_otp()
    db.add(
        OtpChallenge(
            id=challenge_id,
            phone=phone,
            code_hash=hash_otp(str(challenge_id), code),
            ip_hash=ip_hash,
            created_at=now,
            expires_at=now + OTP_TTL,
        )
    )
    await db.commit()
    return OtpIssued(challenge_id, phone, code if user_exists else None)


async def verify_otp(db: AsyncSession, challenge_id: uuid.UUID, code: str, meta: RequestMeta) -> tuple[str, datetime]:
    """Return (raw session token, expiry). The raw token only ever lives in the cookie."""
    invalid = Unauthorized("Wrong or expired OTP", code="otp_invalid")
    now = _now()
    challenge = await db.scalar(select(OtpChallenge).where(OtpChallenge.id == challenge_id).with_for_update())
    if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= now:
        raise invalid
    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        raise TooManyRequests("Too many wrong attempts. Request a new OTP.", code="otp_locked")

    challenge.attempts += 1
    if not otp_matches(str(challenge.id), code, challenge.code_hash):
        await db.commit()
        raise invalid

    challenge.consumed_at = now
    user = await db.scalar(select(User).where(User.phone == challenge.phone, User.is_active.is_(True)))
    if user is None:
        await db.commit()
        raise invalid

    memberships = await _active_memberships(db, user.id)
    only_business = memberships[0][0].business_id if len(memberships) == 1 else None
    token = new_session_token()
    expires_at = now + timedelta(days=get_settings().session_ttl_days)
    db.add(
        UserSession(
            token_hash=hash_session_token(token),
            user_id=user.id,
            business_id=only_business,
            user_agent=(meta.user_agent or "")[:300] or None,
            created_at=now,
            expires_at=expires_at,
        )
    )
    await set_tenant(db, only_business)
    await audit.record_event(
        db,
        meta=meta,
        action="auth.login",
        actor_user_id=user.id,
        business_id=only_business,
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    return token, expires_at


# --- sessions --------------------------------------------------------------------------------------------


async def authenticate(db: AsyncSession, token: str | None) -> tuple[UserSession, User]:
    if not token:
        raise Unauthorized()
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_session_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > _now(),
                User.is_active.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        raise Unauthorized()
    return row[0], row[1]


async def logout(db: AsyncSession, session: UserSession, meta: RequestMeta) -> None:
    session.revoked_at = _now()
    await set_tenant(db, session.business_id)
    await audit.record_event(
        db,
        meta=meta,
        action="auth.logout",
        actor_user_id=session.user_id,
        business_id=session.business_id,
    )


async def _active_memberships(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[Membership, platform.BusinessInfo]]:
    rows = await db.scalars(select(Membership).where(Membership.user_id == user_id, Membership.is_active.is_(True)))
    memberships = list(rows)
    infos = await platform.get_business_infos(db, [m.business_id for m in memberships])
    return [(m, infos[m.business_id]) for m in memberships if m.business_id in infos and infos[m.business_id].is_active]


async def me(db: AsyncSession, session: UserSession, user: User) -> MeOut:
    memberships = await _active_memberships(db, user.id)
    return MeOut(
        id=user.id,
        name=user.name,
        name_ta=user.name_ta,
        language=user.language,
        is_platform_admin=user.is_platform_admin,
        current_business_id=session.business_id,
        memberships=[
            MembershipOut(
                business_id=m.business_id,
                business_name=info.name,
                business_name_ta=info.name_ta,
                role=Role(m.role),
            )
            for m, info in memberships
        ],
    )


async def select_business(db: AsyncSession, session: UserSession, business_id: uuid.UUID) -> None:
    """The client may only pick among its own active memberships; anything else is a 404-equivalent."""
    if await resolve_tenant(db, session.user_id, business_id) is None:
        raise Forbidden("Not a member of this business", code="not_a_member")
    session.business_id = business_id


async def resolve_tenant(db: AsyncSession, user_id: uuid.UUID, business_id: uuid.UUID | None) -> Tenant | None:
    if business_id is None:
        return None
    membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.business_id == business_id,
            Membership.is_active.is_(True),
        )
    )
    if membership is None:
        return None
    info = (await platform.get_business_infos(db, [business_id])).get(business_id)
    if info is None or not info.is_active:
        return None
    return Tenant(
        business_id=business_id,
        role=membership.role,
        location_ids=tuple(membership.location_ids) if membership.location_ids is not None else None,
        enabled_modules=info.enabled_modules,
    )


def actor_of(user: User) -> Actor:
    return Actor(user_id=user.id, is_platform_admin=user.is_platform_admin)


# --- permission checks (service layer) -------------------------------------------------------------------


def require_permission(ctx: Ctx, perm: Perm) -> None:
    if not role_has(ctx.tenant.role, perm):
        raise Forbidden("You don't have permission to do this", code="permission_denied")


def require_module(ctx: Ctx, module: ModuleKey) -> None:
    if module.value not in ctx.tenant.enabled_modules:
        raise Forbidden("This module is not enabled for your business", code="module_disabled")


def permissions_of(role: str) -> list[str]:
    return sorted(p.value for p in Perm if role_has(role, p))


# --- membership management (platform admin) -------------------------------------------------------------


async def add_member(ctx: PlatformCtx, business_id: uuid.UUID, data: MemberIn) -> MemberOut:
    phone = _phone_or_422(data.phone)
    await platform.get_business(ctx.db, business_id)  # 404 if missing
    user = await ctx.db.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone, name=data.name, name_ta=data.name_ta)
        ctx.db.add(user)
        await ctx.db.flush()
    membership = await ctx.db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.business_id == business_id)
    )
    before = MemberOut.model_validate(membership) if membership else None
    if membership is None:
        membership = Membership(user_id=user.id, business_id=business_id, role=data.role.value)
        ctx.db.add(membership)
    membership.role = data.role.value
    membership.location_ids = data.location_ids
    membership.is_active = True
    await ctx.db.flush()
    out = MemberOut.model_validate(membership)
    await set_tenant(ctx.db, business_id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="member.upsert",
        actor_user_id=ctx.actor.user_id,
        business_id=business_id,
        entity_type="membership",
        entity_id=membership.id,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out
