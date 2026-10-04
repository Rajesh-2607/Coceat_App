"""Username and password login, sessions, memberships and permission checks.

Auth flows commit themselves: failure state (the failed-login counter) must persist even when the request fails.
Everything else follows the normal rule: services never commit, the router commits once.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.context import Actor, Ctx, PlatformCtx, RequestMeta, Tenant
from app.core.db import set_tenant
from app.core.errors import Conflict, Forbidden, NotFound, TooManyRequests, Unauthorized, Unprocessable
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_session_token,
    new_session_token,
    normalize_indian_mobile,
    verify_password,
)
from app.modules.accounts.models import Membership, User, UserSession
from app.modules.accounts.permissions import Perm, Role, role_has
from app.modules.accounts.schemas import (
    MemberIn,
    MemberOut,
    MembershipOut,
    MeOut,
    PasswordChangeIn,
    PlatformMembershipOut,
    PlatformUserOut,
    PlatformUserUpdate,
    StaffOut,
    StaffUpdate,
)
from app.modules.audit import service as audit
from app.modules.platform import service as platform
from app.modules.platform.models import Business
from app.modules.platform.modules import ModuleKey

LOCKOUT_AFTER_FAILURES = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(UTC)


def _phone_or_422(raw: str) -> str:
    phone = normalize_indian_mobile(raw)
    if phone is None:
        raise Unprocessable("Enter a valid 10-digit mobile number", code="invalid_phone")
    return phone


# --- login ----------------------------------------------------------------------------------------------


async def login(db: AsyncSession, username: str, password: str, meta: RequestMeta) -> tuple[str, datetime]:
    """Return (raw session token, expiry). Failed attempts are counted and committed before the error is raised."""
    invalid = Unauthorized("Wrong username or password", code="invalid_credentials")
    now = _now()
    user = await db.scalar(select(User).where(User.username == username.strip().lower()).with_for_update())
    if user is None or user.password_hash is None or not user.is_active:
        verify_password(password, DUMMY_PASSWORD_HASH)  # same cost whether or not the account exists
        raise invalid
    if user.locked_until is not None and user.locked_until > now:
        raise TooManyRequests("Too many wrong attempts. Try again in a few minutes.", code="account_locked")
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= LOCKOUT_AFTER_FAILURES:
            user.locked_until = now + LOCKOUT_DURATION
            user.failed_logins = 0
        await db.commit()
        raise invalid
    user.failed_logins = 0
    user.locked_until = None
    return await _start_session(db, user, meta, now)


async def _start_session(db: AsyncSession, user: User, meta: RequestMeta, now: datetime) -> tuple[str, datetime]:
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


async def change_password(
    db: AsyncSession, session: UserSession, user: User, data: PasswordChangeIn, meta: RequestMeta
) -> None:
    if user.password_hash is None or not verify_password(data.current_password, user.password_hash):
        raise Unprocessable("Your current password is wrong", code="wrong_current_password")
    user.password_hash = hash_password(data.new_password)
    await audit.record_event(
        db,
        meta=meta,
        action="auth.password_change",
        actor_user_id=user.id,
        business_id=session.business_id,
        entity_type="user",
        entity_id=user.id,
    )


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


# --- membership management -------------------------------------------------------------------------------
# Memberships are platform rows (not RLS-protected): every query below filters on business_id explicitly.


def _staff_out(m: Membership, u: User) -> StaffOut:
    return StaffOut(
        membership_id=m.id,
        user_id=u.id,
        name=u.name,
        name_ta=u.name_ta,
        phone=u.phone,
        username=u.username,
        role=Role(m.role),
        location_ids=m.location_ids,
        is_active=m.is_active,
    )


async def list_staff(db: AsyncSession, business_id: uuid.UUID) -> list[StaffOut]:
    rows = await db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.business_id == business_id)
        .order_by(Membership.created_at)
    )
    return [_staff_out(m, u) for m, u in rows]


async def _staff_row(db: AsyncSession, business_id: uuid.UUID, membership_id: uuid.UUID) -> tuple[Membership, User]:
    row = (
        await db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id == membership_id, Membership.business_id == business_id)
        )
    ).first()
    if row is None:
        raise NotFound("Staff member not found")
    return row[0], row[1]


async def _in_other_business(db: AsyncSession, user_id: uuid.UUID, business_id: uuid.UUID) -> bool:
    count = await db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.user_id == user_id, Membership.business_id != business_id)
    )
    return bool(count)


ACCOUNT_IN_USE = "This person already has an account used elsewhere. They must change their password themselves."


async def _check_existing_login(
    db: AsyncSession, user: User, business_id: uuid.UUID, username: str, password: str
) -> None:
    """Someone with access to this business may only set credentials for a person whose account is used nowhere
    else. Otherwise an owner could take over a login that also works in another business."""
    if user.username == username and user.password_hash and verify_password(password, user.password_hash):
        return
    if user.is_platform_admin or await _in_other_business(db, user.id, business_id):
        raise Unprocessable(ACCOUNT_IN_USE, code="account_in_use")
    if username != user.username and await db.scalar(
        select(User.id).where(User.username == username, User.id != user.id)
    ):
        raise Conflict("That username is already taken", code="username_taken")
    user.username = username
    user.password_hash = hash_password(password)


async def upsert_staff(db: AsyncSession, business_id: uuid.UUID, data: MemberIn) -> tuple[StaffOut | None, StaffOut]:
    """Add (or re-activate and update) a member of a business, creating the user by phone if needed."""
    phone = _phone_or_422(data.phone)
    username = data.username.strip().lower()
    user = await db.scalar(select(User).where(User.phone == phone))
    if user is None:
        if await db.scalar(select(User.id).where(User.username == username)):
            raise Conflict("That username is already taken", code="username_taken")
        user = User(
            phone=phone,
            name=data.name,
            name_ta=data.name_ta,
            username=username,
            password_hash=hash_password(data.password),
        )
        db.add(user)
        await db.flush()
    else:
        await _check_existing_login(db, user, business_id, username, data.password)
    membership = await db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.business_id == business_id)
    )
    before = _staff_out(membership, user) if membership else None
    if membership is None:
        membership = Membership(user_id=user.id, business_id=business_id, role=data.role.value)
        db.add(membership)
    elif membership.role == Role.OWNER.value and membership.is_active and data.role != Role.OWNER:
        await _ensure_another_owner(db, business_id, membership.id)
    membership.role = data.role.value
    membership.location_ids = data.location_ids
    membership.is_active = True
    await db.flush()
    await db.refresh(membership)
    return before, _staff_out(membership, user)


async def _ensure_another_owner(db: AsyncSession, business_id: uuid.UUID, membership_id: uuid.UUID) -> None:
    """A business must always keep one active owner (else nobody can manage staff)."""
    other = await db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.business_id == business_id,
            Membership.role == Role.OWNER.value,
            Membership.is_active.is_(True),
            Membership.id != membership_id,
        )
    )
    if not other:
        raise Unprocessable("A business needs at least one active owner", code="last_owner")


async def update_staff(
    db: AsyncSession,
    business_id: uuid.UUID,
    membership_id: uuid.UUID,
    data: StaffUpdate,
    *,
    forbid_user_id: uuid.UUID | None = None,
) -> tuple[StaffOut, StaffOut]:
    membership, user = await _staff_row(db, business_id, membership_id)
    if forbid_user_id is not None and membership.user_id == forbid_user_id:
        raise Unprocessable("You cannot change your own access", code="cannot_edit_self")
    before = _staff_out(membership, user)
    changes = data.model_fields_set
    new_role = data.role.value if "role" in changes and data.role is not None else membership.role
    new_active = data.is_active if "is_active" in changes and data.is_active is not None else membership.is_active
    loses_owner = (
        membership.role == Role.OWNER.value
        and membership.is_active
        and (new_role != Role.OWNER.value or not new_active)
    )
    if loses_owner:
        await _ensure_another_owner(db, business_id, membership.id)
    if "password" in changes and data.password is not None:
        if user.is_platform_admin or await _in_other_business(db, user.id, business_id):
            raise Unprocessable(ACCOUNT_IN_USE, code="account_in_use")
        user.password_hash = hash_password(data.password)
    membership.role = new_role
    membership.is_active = new_active
    if "location_ids" in changes:
        membership.location_ids = data.location_ids  # None = all locations
    await db.flush()
    await db.refresh(membership)
    return before, _staff_out(membership, user)


async def add_member(ctx: PlatformCtx, business_id: uuid.UUID, data: MemberIn) -> MemberOut:
    """Platform admin: add a member to any business."""
    await platform.get_business(ctx.db, business_id)  # 404 if missing
    before, after = await upsert_staff(ctx.db, business_id, data)
    out = MemberOut(
        id=after.membership_id,
        user_id=after.user_id,
        business_id=business_id,
        role=after.role,
        location_ids=after.location_ids,
        is_active=after.is_active,
    )
    await set_tenant(ctx.db, business_id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="member.upsert",
        actor_user_id=ctx.actor.user_id,
        business_id=business_id,
        entity_type="membership",
        entity_id=after.membership_id,
        before=audit.snapshot(before),
        after=audit.snapshot(after),
    )
    return out


async def admin_update_staff(
    ctx: PlatformCtx, business_id: uuid.UUID, membership_id: uuid.UUID, data: StaffUpdate
) -> StaffOut:
    await platform.get_business(ctx.db, business_id)
    before, after = await update_staff(ctx.db, business_id, membership_id, data)
    await set_tenant(ctx.db, business_id)
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="member.update",
        actor_user_id=ctx.actor.user_id,
        business_id=business_id,
        entity_type="membership",
        entity_id=membership_id,
        before=audit.snapshot(before),
        after=audit.snapshot(after),
    )
    return after


async def member_counts_by_business(db: AsyncSession, business_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """For the admin console: active membership count per business. Memberships are a platform table (no RLS)."""
    if not business_ids:
        return {}
    rows = await db.execute(
        select(Membership.business_id, func.count())
        .where(Membership.business_id.in_(business_ids), Membership.is_active.is_(True))
        .group_by(Membership.business_id)
    )
    return dict(rows.all())


async def user_names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display names for audit / history views."""
    if not user_ids:
        return {}
    rows = await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
    return {uid: name for uid, name in rows}


# --- platform users (cross-business, for /admin) ----------------------------------------------------------


async def _platform_users_out(db: AsyncSession, users: list[User]) -> list[PlatformUserOut]:
    ids = [u.id for u in users]
    by_user: dict[uuid.UUID, list[PlatformMembershipOut]] = {i: [] for i in ids}
    if ids:
        rows = (
            await db.execute(
                select(Membership, Business.name)
                .join(Business, Business.id == Membership.business_id)
                .where(Membership.user_id.in_(ids))
                .order_by(Business.name)
            )
        ).all()
        for m, business_name in rows:
            by_user[m.user_id].append(
                PlatformMembershipOut(
                    business_id=m.business_id, business_name=business_name, role=Role(m.role), is_active=m.is_active
                )
            )
    return [PlatformUserOut.model_validate({**u.__dict__, "memberships": by_user[u.id]}) for u in users]


async def list_platform_users(ctx: PlatformCtx, *, q: str | None, limit: int = 200) -> list[PlatformUserOut]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.name.ilike(like), User.phone.ilike(like)))
    return await _platform_users_out(ctx.db, list(await ctx.db.scalars(stmt)))


async def update_platform_user(ctx: PlatformCtx, user_id: uuid.UUID, data: PlatformUserUpdate) -> PlatformUserOut:
    """Only a platform admin reaches this, and they can never touch their own account here (below), so an admin
    can always demote or deactivate someone else, but never the last one: reaching zero would need the last
    remaining admin to edit themselves, which is exactly what is blocked."""
    user = await ctx.db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    changes = data.model_fields_set
    if user.id == ctx.actor.user_id and changes & {"is_active", "is_platform_admin"}:
        raise Unprocessable("You cannot change your own account here", code="cannot_edit_self")
    before = (await _platform_users_out(ctx.db, [user]))[0]
    if "is_active" in changes and data.is_active is not None:
        user.is_active = data.is_active
    if "is_platform_admin" in changes and data.is_platform_admin is not None:
        user.is_platform_admin = data.is_platform_admin
    if "platform_role_title" in changes:
        user.platform_role_title = data.platform_role_title
    if "platform_scope_note" in changes:
        user.platform_scope_note = data.platform_scope_note
    await ctx.db.flush()
    await ctx.db.refresh(user)
    out = (await _platform_users_out(ctx.db, [user]))[0]
    await audit.record_event(
        ctx.db,
        meta=ctx.meta,
        action="platform_user.update",
        actor_user_id=ctx.actor.user_id,
        business_id=None,
        entity_type="user",
        entity_id=user.id,
        before=audit.snapshot(before),
        after=audit.snapshot(out),
    )
    return out
