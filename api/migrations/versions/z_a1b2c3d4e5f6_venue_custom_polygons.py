"""venue + job custom footprint/stage polygons

Revision ID: z_a1b2c3d4e5f6
Revises: z9b0c1d2e3f4

A venue (and the job it is assigned to) can describe its footprint and stage as a
drawn polygon instead of only a rectangle. These polygons are stored as JSON arrays
of [x, y] points in centimetres: the footprint in venue coordinates, the stage in
stage-relative coordinates. They are empty for the rectangular/arena/etc. presets.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z_a1b2c3d4e5f6"
down_revision: str | None = "z9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venues",
        sa.Column(
            "footprint_polygon",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "venues",
        sa.Column(
            "stage_polygon",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "production_jobs",
        sa.Column(
            "venue_footprint_polygon",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "production_jobs",
        sa.Column(
            "venue_stage_polygon",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("production_jobs", "venue_stage_polygon")
    op.drop_column("production_jobs", "venue_footprint_polygon")
    op.drop_column("venues", "stage_polygon")
    op.drop_column("venues", "footprint_polygon")
