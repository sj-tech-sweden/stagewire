"""video input lists, inputs and patch points; cameras on the stage plot

Revision ID: c9d0e1f2a3b4
Revises: z0a1b2c3d4e5
Create Date: 2026-10-26 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_input_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["production_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_input_lists_job_id", "video_input_lists", ["job_id"])
    op.create_table(
        "video_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("input_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("source_label", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default=sa.text("'camera'")),
        sa.Column("connector", sa.String(length=64), nullable=False, server_default=sa.text("'sdi'")),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=sa.text("''")),
        sa.ForeignKeyConstraint(["list_id"], ["video_input_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_inputs_list_id", "video_inputs", ["list_id"])
    op.create_table(
        "video_patch_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("connector", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("patch_label", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=sa.text("''")),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["input_id"], ["video_inputs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["audio_devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_patch_points_input_id", "video_patch_points", ["input_id"])
    op.create_index("ix_video_patch_points_device_id", "video_patch_points", ["device_id"])
    op.add_column("stage_plot_elements", sa.Column("linked_video_input_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_stage_plot_elements_linked_video_input_id",
        "stage_plot_elements",
        "video_inputs",
        ["linked_video_input_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_stage_plot_elements_linked_video_input_id", "stage_plot_elements", type_="foreignkey"
    )
    op.drop_column("stage_plot_elements", "linked_video_input_id")
    op.drop_index("ix_video_patch_points_device_id", table_name="video_patch_points")
    op.drop_index("ix_video_patch_points_input_id", table_name="video_patch_points")
    op.drop_table("video_patch_points")
    op.drop_index("ix_video_inputs_list_id", table_name="video_inputs")
    op.drop_table("video_inputs")
    op.drop_index("ix_video_input_lists_job_id", table_name="video_input_lists")
    op.drop_table("video_input_lists")
