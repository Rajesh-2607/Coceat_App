"""Engine, sessions and tenant isolation.

Tenant isolation has three layers:
1. ``do_orm_execute`` adds ``business_id = <current>`` to every ORM query touching a ``TenantMixin`` model.
2. ``before_flush`` stamps new tenant rows with the current business and refuses cross-tenant writes.
3. Postgres RLS: ``after_begin`` runs ``set_config('app.business_id', ..., true)`` (transaction-local, safe
   with Neon's transaction-mode pooler) and every tenant table has a FORCE'd policy on it.

With no business in context all three fail closed: queries return nothing and writes raise.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, event, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    ORMExecuteState,
    Session,
    SessionTransaction,
    mapped_column,
    with_loader_criteria,
)

from app.core.config import get_settings
from app.core.ids import uuid7

TENANT_KEY = "business_id"

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012  # SQLAlchemy's declared class attribute
        uuid.UUID: PG_UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[str]: JSONB,
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TenantMixin:
    """Every tenant-owned table inherits this. Its migration must also call enable_tenant_rls (see 0001)."""

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="RESTRICT"), index=True)


class TenantContextError(RuntimeError):
    """Raised when tenant data is written without, or outside, the current business."""


# --- tenant session events -------------------------------------------------------------------------------


@event.listens_for(Session, "do_orm_execute")
def _add_tenant_criteria(state: ORMExecuteState) -> None:
    if state.is_column_load or state.is_relationship_load:
        return  # the criteria option already propagates to these
    if not (state.is_select or state.is_update or state.is_delete):
        return
    business_id = state.session.info.get(TENANT_KEY)
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: cls.business_id == business_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _stamp_tenant(session: Session, _flush_context: object, _instances: object) -> None:
    business_id = session.info.get(TENANT_KEY)
    for obj in session.new:
        if not isinstance(obj, TenantMixin):
            continue
        if business_id is None:
            raise TenantContextError(f"cannot create {type(obj).__name__} without a current business")
        if obj.business_id is None:
            obj.business_id = business_id
        elif obj.business_id != business_id:
            raise TenantContextError(f"cannot create {type(obj).__name__} for another business")
    for obj in session.dirty | session.deleted:
        if isinstance(obj, TenantMixin) and obj.business_id != business_id:
            raise TenantContextError(f"cannot modify {type(obj).__name__} of another business")


@event.listens_for(Session, "after_begin")
def _set_rls_context(session: Session, _txn: SessionTransaction, connection: Connection) -> None:
    business_id = session.info.get(TENANT_KEY)
    if business_id is not None:
        connection.execute(text("SELECT set_config('app.business_id', :b, true)"), {"b": str(business_id)})


async def set_tenant(session: AsyncSession, business_id: uuid.UUID | None) -> None:
    """Bind the session (current and future transactions) to one business."""
    session.info[TENANT_KEY] = business_id
    if session.in_transaction():
        await session.execute(
            text("SELECT set_config('app.business_id', :b, true)"),
            {"b": str(business_id) if business_id else ""},
        )


# --- engine / sessions -----------------------------------------------------------------------------------


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # Neon computes scale to zero and drop idle connections
        pool_recycle=300,
        # Neon's pooler is PgBouncer in transaction mode: server-side prepared statements are unsafe.
        connect_args={"prepare_threshold": None},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped session. Services commit explicitly: one commit per business action."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
