"""drop the legacy rigging_points table

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2

Rigging points live on the graph (``graph/rigging_native.py``); every row was imported there
(``scripts/parity_check.py`` showed no difference first) and the columns that point at them
(``rigging_point_id`` on devices, fixtures and plot elements) lost their foreign keys in
``q7r8s9t0u1v2``.

This is destructive. The downgrade recreates the table **empty**: restore the pre-drop dump
(``backups/stagewire-pre-rigging-points-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r8s9t0u1v2w3"
down_revision: str | None = "q7r8s9t0u1v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("rigging_points")


def downgrade() -> None:
    op.create_table(
        "rigging_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("trim_height_cm", sa.Float(), nullable=True),
        sa.Column("weight_capacity_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_rigging_points_job_id", "rigging_points", ["job_id"])
