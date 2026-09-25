"""Alembic runs with the owner role over Neon's DIRECT (non-pooled) connection."""

from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  # registers every model on Base.metadata
from alembic import context
from app.core.config import get_settings
from app.core.db import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("url") or get_settings().database_url_direct.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # lock_timeout: fail fast instead of queueing behind live traffic's locks. Set via startup options:
    # executing SET here would autobegin a transaction that Alembic then never commits.
    engine = create_engine(_url(), poolclass=pool.NullPool, connect_args={"options": "-c lock_timeout=10s"})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
