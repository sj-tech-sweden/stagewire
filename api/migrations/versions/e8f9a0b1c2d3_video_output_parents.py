"""parent step on video output chain steps, so outputs can split

Existing chains are straight lines, so each step's parent is the step before it.

Revision ID: e8f9a0b1c2d3
Revises: d6e7f8a9b0c1
Create Date: 2026-10-29 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_output_patch_points",
        sa.Column("parent_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_video_output_patch_points_parent_id",
        "video_output_patch_points",
        "video_output_patch_points",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_video_output_patch_points_parent_id",
        "video_output_patch_points",
        ["parent_id"],
    )
    op.execute(
        """
        UPDATE video_output_patch_points AS p
        SET parent_id = sub.prev_id
        FROM (
            SELECT id,
                   LAG(id) OVER (PARTITION BY output_id ORDER BY position) AS prev_id
            FROM video_output_patch_points
        ) AS sub
        WHERE p.id = sub.id AND sub.prev_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_video_output_patch_points_parent_id", table_name="video_output_patch_points")
    op.drop_constraint(
        "fk_video_output_patch_points_parent_id",
        "video_output_patch_points",
        type_="foreignkey",
    )
    op.drop_column("video_output_patch_points", "parent_id")
