"""speaker coverage fields and output patch point link for stage plot elements

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-10-25 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "y9z0a1b2c3d4"
down_revision: str | None = "x8y9z0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stage_plot_elements",
        sa.Column("coverage_angle_h", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "stage_plot_elements",
        sa.Column("coverage_distance_m", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "stage_plot_elements",
        sa.Column("linked_output_point_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_stage_plot_elements_linked_output_point_id",
        "stage_plot_elements",
        "output_patch_points",
        ["linked_output_point_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_stage_plot_elements_linked_output_point_id",
        "stage_plot_elements",
        type_="foreignkey",
    )
    op.drop_column("stage_plot_elements", "linked_output_point_id")
    op.drop_column("stage_plot_elements", "coverage_distance_m")
    op.drop_column("stage_plot_elements", "coverage_angle_h")
