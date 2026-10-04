"""seed workflow_steps/workflow_highlights/reference units & varieties into vertical_templates.settings

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-29 10:30:00.000000

Config-driven, not code: this is a data migration, not a new column. Any vertical (existing or future)
can have its own steps/highlights/reference lists edited later through PATCH /admin/verticals/{key}.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The same operating flow applies to every wholesale-produce vertical Cocreat supports today; it is stored
# as ordinary settings data (editable per vertical) rather than baked into any module's code.
WORKFLOW_STEPS = [
    {"step": 1, "title": "Purchase"},
    {"step": 2, "title": "Stock Received"},
    {"step": 3, "title": "Stock Assigned to Shop"},
    {"step": 4, "title": "Sale"},
    {"step": 5, "title": "Payment / Credit"},
    {"step": 6, "title": "Return / Wastage"},
]
WORKFLOW_HIGHLIGHTS = [
    {
        "title": "Stock is shop-owned",
        "description": "Every unit is tied to a shop, so transfers and wastage are traceable.",
    },
    {
        "title": "Credit is first-class",
        "description": "Wholesale buyers commonly run on credit — ageing buckets drive collections.",
    },
    {
        "title": "Perishables need loss control",
        "description": "Wastage capture matters at shop level for produce that doesn't keep.",
    },
]

# key -> (reference units, reference varieties) — a starting point shown on the Configuration page only;
# each business still sets up its own catalog in its own workspace.
REFERENCE_CATALOG: dict[str, tuple[list[str], list[str]]] = {
    "banana": (["crates", "kg"], ["Robusta", "Poovan", "Yelakki", "Nendran", "Rasthali"]),
    "tomato": (["crates", "kg"], ["Hybrid", "Desi", "Cherry"]),
    "vegetable": (["crates", "kg", "bags"], ["Onion", "Potato", "Carrot", "Cabbage", "Beans"]),
    "flower": (["bundles", "kg"], ["Jasmine", "Marigold", "Rose", "Chrysanthemum"]),
}


def upgrade() -> None:
    conn = op.get_bind()
    for key, (units, varieties) in REFERENCE_CATALOG.items():
        settings = {
            "reference_units": units,
            "reference_varieties": varieties,
            "workflow_steps": WORKFLOW_STEPS,
            "workflow_highlights": WORKFLOW_HIGHLIGHTS,
        }
        conn.execute(
            sa.text("UPDATE vertical_templates SET settings = CAST(:settings AS jsonb) WHERE key = :key").bindparams(
                settings=json.dumps(settings), key=key
            )
        )
    # any other vertical (created after this migration, or not in the table above) still gets the generic flow
    generic = {
        "reference_units": [],
        "reference_varieties": [],
        "workflow_steps": WORKFLOW_STEPS,
        "workflow_highlights": WORKFLOW_HIGHLIGHTS,
    }
    conn.execute(
        sa.text(
            "UPDATE vertical_templates SET settings = CAST(:settings AS jsonb) WHERE settings = '{}'::jsonb"
        ).bindparams(settings=json.dumps(generic))
    )


def downgrade() -> None:
    op.execute("UPDATE vertical_templates SET settings = '{}'::jsonb")
