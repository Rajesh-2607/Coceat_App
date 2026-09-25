import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from app import models  # noqa: F401
from app.core.db import Base


def test_models_match_migrations() -> None:
    """Fails when a model changed without a migration (run: alembic revision --autogenerate)."""
    engine = create_engine(os.environ["DATABASE_URL_DIRECT"])
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    assert diff == []


def test_every_tenant_table_has_forced_rls() -> None:
    tenant_tables = {
        t.name for t in Base.metadata.tables.values() if "business_id" in t.c and not t.c.business_id.nullable
    } - {"memberships"}  # platform table: looked up across businesses at login
    engine = create_engine(os.environ["DATABASE_URL_DIRECT"])
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity AND relkind = 'r'")
        ).scalars()
        protected = set(rows)
    engine.dispose()
    assert tenant_tables <= protected, f"missing RLS: {tenant_tables - protected}"
