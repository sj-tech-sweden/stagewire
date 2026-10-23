"""add stage dimensions and richer stage-plot elements

Stage size (cm) on the production job so the plot maps to the real venue,
plus per-element size, picture and patch-point link on stage-plot elements.

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r2s3t4u5v6w7"
down_revision: str | None = "q1r2s3t4u5v6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "production_jobs",
        sa.Column("stage_width_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "production_jobs",
        sa.Column("stage_height_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "stage_plot_elements",
        sa.Column(
            "linked_patch_point_id",
            sa.Uuid(),
            sa.ForeignKey("channel_patch_points.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "stage_plot_elements",
        sa.Column("width_cm", sa.Float(), nullable=False, server_default=sa.text("60.0")),
    )
    op.add_column(
        "stage_plot_elements",
        sa.Column("height_cm", sa.Float(), nullable=False, server_default=sa.text("60.0")),
    )
    op.add_column(
        "stage_plot_elements",
        sa.Column(
            "image_url",
            sa.String(length=1024),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    op.drop_column("stage_plot_elements", "image_url")
    op.drop_column("stage_plot_elements", "height_cm")
    op.drop_column("stage_plot_elements", "width_cm")
    op.drop_column("stage_plot_elements", "linked_patch_point_id")
    op.drop_column("production_jobs", "stage_height_cm")
    op.drop_column("production_jobs", "stage_width_cm")
