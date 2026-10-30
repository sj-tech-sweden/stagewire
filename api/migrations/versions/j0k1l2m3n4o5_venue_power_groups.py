"""venue power groups

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j0k1l2m3n4o5"
down_revision: str | None = "i9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_power_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("venue_id", sa.Uuid(), sa.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("rating_amps", sa.Float(), nullable=True),
        sa.Column("phases", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_venue_power_groups_venue_id", "venue_power_groups", ["venue_id"])
    with op.batch_alter_table("venue_power_outlets") as batch:
        batch.add_column(sa.Column("group_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_venue_power_outlets_group_id",
            "venue_power_groups",
            ["group_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_venue_power_outlets_group_id", ["group_id"])
    with op.batch_alter_table("power_nodes") as batch:
        batch.add_column(sa.Column("venue_group_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_power_nodes_venue_group_id",
            "venue_power_groups",
            ["venue_group_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_power_nodes_venue_group_id", ["venue_group_id"])


def downgrade() -> None:
    with op.batch_alter_table("power_nodes") as batch:
        batch.drop_index("ix_power_nodes_venue_group_id")
        batch.drop_constraint("fk_power_nodes_venue_group_id", type_="foreignkey")
        batch.drop_column("venue_group_id")
    with op.batch_alter_table("venue_power_outlets") as batch:
        batch.drop_index("ix_venue_power_outlets_group_id")
        batch.drop_constraint("fk_venue_power_outlets_group_id", type_="foreignkey")
        batch.drop_column("group_id")
    op.drop_index("ix_venue_power_groups_venue_id", table_name="venue_power_groups")
    op.drop_table("venue_power_groups")
