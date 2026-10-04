"""Staff of one business, managed by its owner. (The platform team uses the /admin equivalents.)"""

import uuid

from app.core.context import Ctx
from app.core.errors import Unprocessable
from app.modules.accounts import service as accounts
from app.modules.accounts.permissions import Perm
from app.modules.accounts.schemas import MemberIn, StaffOut, StaffUpdate
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.inventory import service as inventory
from app.modules.platform.modules import ModuleKey


def _view(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STAFF)
    require_permission(ctx, Perm.STAFF_VIEW)


def _manage(ctx: Ctx) -> None:
    require_module(ctx, ModuleKey.STAFF)
    require_permission(ctx, Perm.STAFF_MANAGE)


async def _check_locations(ctx: Ctx, location_ids: list[uuid.UUID] | None) -> None:
    """Every listed location must belong to this business (a foreign id is a 404, like anywhere else)."""
    for location_id in location_ids or []:
        await inventory.require_location(ctx, location_id)


async def list_staff(ctx: Ctx) -> list[StaffOut]:
    _view(ctx)
    return await accounts.list_staff(ctx.db, ctx.tenant.business_id)


async def add_staff(ctx: Ctx, data: MemberIn) -> StaffOut:
    _manage(ctx)
    await _check_locations(ctx, data.location_ids)
    before, after = await accounts.upsert_staff(ctx.db, ctx.tenant.business_id, data)
    if after.user_id == ctx.actor.user_id:
        raise Unprocessable("You cannot change your own access", code="cannot_edit_self")
    await audit.record(
        ctx, "staff.upsert", entity_type="membership", entity_id=after.membership_id, before=before, after=after
    )
    return after


async def update_staff(ctx: Ctx, membership_id: uuid.UUID, data: StaffUpdate) -> StaffOut:
    _manage(ctx)
    await _check_locations(ctx, data.location_ids)
    before, after = await accounts.update_staff(
        ctx.db, ctx.tenant.business_id, membership_id, data, forbid_user_id=ctx.actor.user_id
    )
    await audit.record(
        ctx, "staff.update", entity_type="membership", entity_id=membership_id, before=before, after=after
    )
    return after
