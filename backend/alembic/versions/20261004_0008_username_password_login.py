"""username and password login

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-04 12:00:00.000000

Adds a login name and password hash to users, plus the failed-login counter used for lockout. Phone numbers stay
as contact details. Existing accounts have no username or password yet: a platform admin or owner sets one.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=200), nullable=True))
    op.add_column(
        "users",
        sa.Column("failed_logins", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_check_constraint(
        "ck_users_username",
        "users",
        "username IS NULL OR username ~ '^[a-z0-9._-]{3,40}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_username", "users", type_="check")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_logins")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
