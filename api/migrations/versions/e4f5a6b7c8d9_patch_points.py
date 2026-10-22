"""add channel patch points and drop legacy flat patch fields

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "channel_patch_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("audio_channel_patches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("point_type", sa.String(64), nullable=False, server_default="mixer"),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("patch_label", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.String(2000), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_channel_patch_points_channel_id", "channel_patch_points", ["channel_id"]
    )

    op.drop_column("audio_channel_patches", "connection_type")
    op.drop_column("audio_channel_patches", "connection_details")
    op.drop_column("audio_channel_patches", "stagebox_patch")
    op.drop_column("audio_channel_patches", "foh_patch")
    op.drop_column("audio_channel_patches", "mon_patch")


def downgrade():
    op.add_column(
        "audio_channel_patches",
        sa.Column("connection_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("connection_details", postgresql.JSON(), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("stagebox_patch", sa.String(255), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("foh_patch", sa.String(255), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("mon_patch", sa.String(255), nullable=True),
    )

    op.drop_index("ix_channel_patch_points_channel_id", table_name="channel_patch_points")
    op.drop_table("channel_patch_points")
