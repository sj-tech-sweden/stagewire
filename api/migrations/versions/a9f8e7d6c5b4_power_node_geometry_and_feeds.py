"""power node geometry and merged feeds

Revision ID: a9f8e7d6c5b4
Revises: b1c2d3e4f5g6
Create Date: 2026-10-29 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9f8e7d6c5b4"
down_revision: str | None = "b1c2d3e4f5g6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("power_nodes", sa.Column("x_cm", sa.Float(), nullable=True))
    op.add_column("power_nodes", sa.Column("y_cm", sa.Float(), nullable=True))
    op.create_table(
        "power_node_feeds",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("power_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("power_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feed_connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("phase", sa.String(4), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_power_node_feeds_job_id", "power_node_feeds", ["job_id"])
    op.create_index("ix_power_node_feeds_node_id", "power_node_feeds", ["node_id"])
    op.create_index("ix_power_node_feeds_parent_id", "power_node_feeds", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_power_node_feeds_parent_id", table_name="power_node_feeds")
    op.drop_index("ix_power_node_feeds_node_id", table_name="power_node_feeds")
    op.drop_index("ix_power_node_feeds_job_id", table_name="power_node_feeds")
    op.drop_table("power_node_feeds")
    op.drop_column("power_nodes", "y_cm")
    op.drop_column("power_nodes", "x_cm")
