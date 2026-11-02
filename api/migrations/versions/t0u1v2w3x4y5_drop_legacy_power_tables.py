"""drop the legacy power node and feed tables

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4

Power nodes and their extra feeds live on the graph (``graph/power_native.py``); every row was
imported there (``scripts/parity_check.py`` showed no difference first) and the ``power_node_id``
columns of loads lost their foreign keys in ``s9t0u1v2w3x4``.

This is destructive. The downgrade recreates the two tables **empty**: restore the pre-drop dump
(``backups/stagewire-pre-power-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t0u1v2w3x4y5"
down_revision: str | None = "s9t0u1v2w3x4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("power_node_feeds")  # points at the nodes
    op.drop_table("power_nodes")


def downgrade() -> None:
    op.create_table(
        "power_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("power_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("feed_connector", sa.String(64), nullable=True),
        sa.Column("phase", sa.String(4), nullable=True),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("rating_amps", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "venue_outlet_id",
            sa.Uuid(),
            sa.ForeignKey("venue_power_outlets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "venue_group_id",
            sa.Uuid(),
            sa.ForeignKey("venue_power_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("x_cm", sa.Float(), nullable=True),
        sa.Column("y_cm", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    for column in ("job_id", "parent_id", "venue_outlet_id", "venue_group_id", "device_id"):
        op.create_index(f"ix_power_nodes_{column}", "power_nodes", [column])
    op.create_table(
        "power_node_feeds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.Uuid(),
            sa.ForeignKey("power_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("power_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feed_connector", sa.String(64), nullable=True),
        sa.Column("phase", sa.String(4), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    for column in ("job_id", "node_id", "parent_id"):
        op.create_index(f"ix_power_node_feeds_{column}", "power_node_feeds", [column])
