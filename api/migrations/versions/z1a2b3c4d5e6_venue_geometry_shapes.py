"""venue geometry shapes

Revision ID: z1a2b3c4d5e6
Revises: a9f8e7d6c5b4
Create Date: 2026-11-04 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
# Re-parented onto the trunk tip (a9f8e7d6c5b4) instead of the z0a1b2c3d4e5
# branchpoint. The next migration (z2a3b4c5d6e7, venue base-rig ownership) adds
# venue_id to tables that are only created on the trunk (e.g. video_input_lists at
# c9d0e1f2a3b4). Branching off z0a1 let alembic schedule z2 before those trunk
# table creations, so the ALTER failed with "relation does not exist". Keeping the
# venue branch after the full trunk guarantees every referenced table exists.
down_revision: str | None = "a9f8e7d6c5b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venues",
        sa.Column(
            "footprint_shape",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'rectangular'"),
        ),
    )
    op.add_column(
        "venues",
        sa.Column(
            "stage_shape",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'proscenium'"),
        ),
    )
    op.add_column(
        "production_jobs",
        sa.Column(
            "venue_footprint_shape",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'rectangular'"),
        ),
    )
    op.add_column(
        "production_jobs",
        sa.Column(
            "venue_stage_shape",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'proscenium'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("production_jobs", "venue_stage_shape")
    op.drop_column("production_jobs", "venue_footprint_shape")
    op.drop_column("venues", "stage_shape")
    op.drop_column("venues", "footprint_shape")
