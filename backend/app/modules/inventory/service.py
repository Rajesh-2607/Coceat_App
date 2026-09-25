import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.context import Ctx
from app.core.errors import Conflict, NotFound
from app.modules.accounts.permissions import Perm
from app.modules.accounts.service import require_module, require_permission
from app.modules.audit import service as audit
from app.modules.inventory.models import Location
from app.modules.inventory.schemas import LocationCreate, LocationOut, LocationUpdate
from app.modules.platform.modules import ModuleKey


async def _get(ctx: Ctx, location_id: uuid.UUID) -> Location:
    # tenant criteria + RLS make another business's row indistinguishable from a missing one
    location = await ctx.db.scalar(select(Location).where(Location.id == location_id))
    if location is None or not ctx.can_access_location(location.id):
        raise NotFound("Location not found")
    return location


async def list_locations(ctx: Ctx) -> list[LocationOut]:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_VIEW)
    rows = await ctx.db.scalars(select(Location).order_by(Location.name))
    return [LocationOut.model_validate(r) for r in rows if ctx.can_access_location(r.id)]


async def get_location(ctx: Ctx, location_id: uuid.UUID) -> LocationOut:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_VIEW)
    return LocationOut.model_validate(await _get(ctx, location_id))


async def _flush_unique(ctx: Ctx) -> None:
    try:
        async with ctx.db.begin_nested():
            await ctx.db.flush()
    except IntegrityError as exc:
        raise Conflict("A location with this name already exists", code="location_name_taken") from exc


async def create_location(ctx: Ctx, data: LocationCreate) -> LocationOut:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_MANAGE)
    location = Location(**data.model_dump())
    ctx.db.add(location)
    await _flush_unique(ctx)
    await ctx.db.refresh(location)
    out = LocationOut.model_validate(location)
    await audit.record(ctx, "location.create", entity_type="location", entity_id=location.id, after=out)
    return out


async def update_location(ctx: Ctx, location_id: uuid.UUID, data: LocationUpdate) -> LocationOut:
    require_module(ctx, ModuleKey.STOCK)
    require_permission(ctx, Perm.LOCATIONS_MANAGE)
    location = await _get(ctx, location_id)
    before = LocationOut.model_validate(location)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field != "name_ta":
            continue  # only name_ta is clearable
        setattr(location, field, value)
    await _flush_unique(ctx)
    await ctx.db.refresh(location)
    out = LocationOut.model_validate(location)
    await audit.record(ctx, "location.update", entity_type="location", entity_id=location.id, before=before, after=out)
    return out
