"""camera and lens values on devices; lens and focal length on stage plot elements

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-27 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("sensor_width_mm", "focal_min_mm", "focal_max_mm", "max_distance_m"):
        op.add_column("audio_devices", sa.Column(column, sa.Float(), nullable=True))
    op.add_column("stage_plot_elements", sa.Column("linked_lens_device_id", sa.Uuid(), nullable=True))
    op.add_column("stage_plot_elements", sa.Column("focal_mm", sa.Float(), nullable=True))
    op.create_foreign_key(
        "fk_stage_plot_elements_linked_lens_device_id",
        "stage_plot_elements",
        "audio_devices",
        ["linked_lens_device_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_stage_plot_elements_linked_lens_device_id", "stage_plot_elements", type_="foreignkey"
    )
    op.drop_column("stage_plot_elements", "focal_mm")
    op.drop_column("stage_plot_elements", "linked_lens_device_id")
    for column in ("max_distance_m", "focal_max_mm", "focal_min_mm", "sensor_width_mm"):
        op.drop_column("audio_devices", column)
