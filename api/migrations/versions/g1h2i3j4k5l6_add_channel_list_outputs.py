"""add channel list outputs and output patch points

Revision ID: g1h2i3j4k5l6
Revises: f5a6b7c8d9e0
Create Date: 2026-10-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "g1h2i3j4k5l6"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.execute("DROP TABLE IF EXISTS channel_output_points CASCADE")
    op.execute("DROP TABLE IF EXISTS channel_output_chains CASCADE")

    op.create_table(
        "channel_list_outputs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "channel_list_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("audio_channel_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Output"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connector", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("color_code", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_channel_list_outputs_channel_list_id",
        "channel_list_outputs",
        ["channel_list_id"],
    )

    op.create_table(
        "output_patch_points",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "output_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("channel_list_outputs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("point_type", sa.String(length=64), nullable=False, server_default="mixer"),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("connector", sa.String(length=64), nullable=True),
        sa.Column("patch_label", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_output_patch_points_output_id",
        "output_patch_points",
        ["output_id"],
    )


def downgrade() -> Sequence:
    op.drop_table("output_patch_points")
    op.drop_table("channel_list_outputs")
