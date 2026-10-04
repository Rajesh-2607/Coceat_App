"""Small helpers shared by module services."""

from sqlalchemy.exc import IntegrityError

from app.core.context import Ctx
from app.core.errors import Conflict


async def flush_unique(ctx: Ctx, message: str, code: str) -> None:
    """Flush pending rows; a unique-constraint clash becomes a 409 with a stable code (savepoint keeps the txn)."""
    try:
        async with ctx.db.begin_nested():
            await ctx.db.flush()
    except IntegrityError as exc:
        raise Conflict(message, code=code) from exc
