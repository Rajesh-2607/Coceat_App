"""platform settings, payment status, platform-team descriptive fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# platform_settings is a platform table (no business_id, no RLS) — same as businesses and vertical_templates.


def upgrade() -> None:
    op.add_column(
        "subscriptions", sa.Column("payment_status", sa.String(length=10), nullable=False, server_default="ok")
    )
    op.alter_column("subscriptions", "payment_status", server_default=None)
    op.create_check_constraint("ck_subscriptions_payment_status", "subscriptions", "payment_status IN ('ok', 'failed')")

    op.add_column("users", sa.Column("platform_role_title", sa.String(length=60), nullable=True))
    op.add_column("users", sa.Column("platform_scope_note", sa.String(length=120), nullable=True))

    op.create_table(
        "platform_settings",
        sa.Column("id", sa.String(length=10), nullable=False),
        sa.Column("platform_name", sa.String(length=120), nullable=False),
        sa.Column("support_email", sa.String(length=200), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("default_trial_days", sa.Integer(), nullable=False),
        sa.Column("default_plan_key", sa.String(length=40), nullable=True),
        sa.Column("invoice_prefix", sa.String(length=20), nullable=False),
        sa.Column("gst_rate_bp", sa.Integer(), nullable=False),
        sa.Column("grace_period_days", sa.Integer(), nullable=False),
        sa.Column("notification_prefs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("gst_rate_bp >= 0 AND gst_rate_bp <= 10000", name=op.f("ck_platform_settings_gst_rate_bp")),
        sa.CheckConstraint("default_trial_days > 0", name=op.f("ck_platform_settings_default_trial_days")),
        sa.CheckConstraint("grace_period_days >= 0", name=op.f("ck_platform_settings_grace_period_days")),
        sa.ForeignKeyConstraint(
            ["default_plan_key"],
            ["subscription_plans.key"],
            name=op.f("fk_platform_settings_default_plan_key_subscription_plans"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_settings")),
    )

    notification_defaults = (
        '{"trial_expiring": {"email": true, "slack": true}, '
        '"payment_failure": {"email": true, "slack": true}, '
        '"setup_completed": {"email": true, "slack": true}, '
        '"module_toggled": {"email": true, "slack": true}}'
    )
    op.execute(
        f"""
        INSERT INTO platform_settings
            (id, platform_name, support_email, default_currency, default_trial_days, default_plan_key,
             invoice_prefix, gst_rate_bp, grace_period_days, notification_prefs, created_at, updated_at)
        VALUES
            ('default', 'Cocreat Business OS', 'support@cocreat.in', 'INR', 14, 'basic',
             'COC/26-27/', 1800, 7, '{notification_defaults}'::jsonb, now(), now())
        """
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_column("users", "platform_scope_note")
    op.drop_column("users", "platform_role_title")
    op.drop_constraint("ck_subscriptions_payment_status", "subscriptions", type_="check")
    op.drop_column("subscriptions", "payment_status")
