"""video outputs with patch points; switcher product on video input lists

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-26 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video_input_lists", sa.Column("switcher_product_id", sa.String(length=64), nullable=True))
    op.add_column("video_input_lists", sa.Column("switcher_product_name", sa.String(length=255), nullable=True))
    op.add_column("video_input_lists", sa.Column("switcher_inputs", sa.Integer(), nullable=True))
    op.add_column("video_input_lists", sa.Column("switcher_outputs", sa.Integer(), nullable=True))
    op.create_table(
        "video_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("list_id", sa.Uuid(), nullable=False),
        sa.Column("output_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("destination_label", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("connector", sa.String(length=64), nullable=False, server_default=sa.text("'sdi'")),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=sa.text("''")),
        sa.ForeignKeyConstraint(["list_id"], ["video_input_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_outputs_list_id", "video_outputs", ["list_id"])
    op.create_table(
        "video_output_patch_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("output_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("connector", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("patch_label", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=sa.text("''")),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["output_id"], ["video_outputs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["audio_devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_output_patch_points_output_id", "video_output_patch_points", ["output_id"])
    op.create_index("ix_video_output_patch_points_device_id", "video_output_patch_points", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_video_output_patch_points_device_id", table_name="video_output_patch_points")
    op.drop_index("ix_video_output_patch_points_output_id", table_name="video_output_patch_points")
    op.drop_table("video_output_patch_points")
    op.drop_index("ix_video_outputs_list_id", table_name="video_outputs")
    op.drop_table("video_outputs")
    op.drop_column("video_input_lists", "switcher_outputs")
    op.drop_column("video_input_lists", "switcher_inputs")
    op.drop_column("video_input_lists", "switcher_product_name")
    op.drop_column("video_input_lists", "switcher_product_id")
