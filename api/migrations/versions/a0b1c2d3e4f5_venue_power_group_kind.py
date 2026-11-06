"""classify venue power groups as incoming / panel / group

Revision ID: a0b1c2d3e4f5
Revises: z_b2c3d4e5f6a7

A venue's supply tree now has three node kinds so the UI can model a real install:
'incoming' (the mains), 'panel' (a distribution board that may feed another panel), and
'group' (a fused circuit inside a panel that outlets plug into). ``kind`` replaces the
ambiguity of calling every node a "group" and lets the API enforce that outlets connect to
circuits, not to panels, and that panels hang off the incoming supply or another panel.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "z_b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venue_power_groups",
        sa.Column("kind", sa.String(16), nullable=False, server_default="group"),
    )
    op.create_index("ix_venue_power_groups_kind", "venue_power_groups", ["kind"])
    # Backfill the existing tree: incoming stays incoming; a node with no parent becomes a panel
    # (board) and any node with a parent becomes a circuit (group) living inside that panel.
    op.execute("UPDATE venue_power_groups SET kind='incoming' WHERE is_incoming = true")
    op.execute(
        "UPDATE venue_power_groups SET kind='panel' WHERE is_incoming = false AND parent_id IS NULL"
    )
    op.execute(
        "UPDATE venue_power_groups SET kind='group' WHERE is_incoming = false"
        " AND parent_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_venue_power_groups_kind", table_name="venue_power_groups")
    op.drop_column("venue_power_groups", "kind")
