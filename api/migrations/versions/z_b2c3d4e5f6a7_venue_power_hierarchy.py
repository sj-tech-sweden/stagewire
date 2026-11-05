"""venue power hierarchy: parent groups and an incoming supply

Revision ID: z_b2c3d4e5f6a7
Revises: z_a1b2c3d4e5f6

A venue's power is a tree, not a flat list of circuits. A panel can sit under another
panel (or under the incoming supply) so a venue can model "incoming 50A -> panel A 32A
-> panel B 32A". ``parent_id`` is a self-referential FK (SET NULL if the parent is
removed). ``is_incoming`` flags the single supply the whole venue draws from; its load
is every outlet's rating summed across the whole tree, so the UI can warn when the
panels are each within their own breaker yet the total exceeds the incoming supply.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z_b2c3d4e5f6a7"
down_revision: str | None = "z_a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venue_power_groups",
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("venue_power_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_venue_power_groups_parent_id", "venue_power_groups", ["parent_id"])
    op.add_column(
        "venue_power_groups",
        sa.Column("is_incoming", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("venue_power_groups", "is_incoming")
    op.drop_index("ix_venue_power_groups_parent_id", table_name="venue_power_groups")
    op.drop_column("venue_power_groups", "parent_id")
