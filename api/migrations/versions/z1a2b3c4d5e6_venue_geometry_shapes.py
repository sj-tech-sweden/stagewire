"""venue geometry shapes

Revision ID: z1a2b3c4d5e6
Revises: z0a1b2c3d4e5
Create Date: 2026-11-04 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: str | None = "z0a1b2c3d4e5"
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
