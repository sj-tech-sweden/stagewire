"""add stockwire product link columns for channels, patch points, mixer

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "m7n8o9p0q1r2"
down_revision: str | None = "l6m7n8o9p0q1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "audio_channel_lists",
        sa.Column("mixer_product_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_audio_channel_lists_mixer_product_id", "audio_channel_lists", ["mixer_product_id"])
    op.add_column(
        "audio_channel_lists",
        sa.Column("mixer_product_name", sa.String(length=255), nullable=True),
    )

    op.add_column(
        "audio_channel_patches",
        sa.Column("stockwire_product_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_audio_channel_patches_stockwire_product_id",
        "audio_channel_patches",
        ["stockwire_product_id"],
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("stockwire_product_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("stand_product_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_audio_channel_patches_stand_product_id",
        "audio_channel_patches",
        ["stand_product_id"],
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("stand_product_name", sa.String(length=255), nullable=True),
    )

    op.add_column(
        "channel_patch_points",
        sa.Column("stockwire_product_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_channel_patch_points_stockwire_product_id",
        "channel_patch_points",
        ["stockwire_product_id"],
    )
    op.add_column(
        "channel_patch_points",
        sa.Column("stockwire_product_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channel_patch_points", "stockwire_product_name")
    op.drop_index("ix_channel_patch_points_stockwire_product_id", table_name="channel_patch_points")
    op.drop_column("channel_patch_points", "stockwire_product_id")

    op.drop_column("audio_channel_patches", "stand_product_name")
    op.drop_index("ix_audio_channel_patches_stand_product_id", table_name="audio_channel_patches")
    op.drop_column("audio_channel_patches", "stand_product_id")
    op.drop_column("audio_channel_patches", "stockwire_product_name")
    op.drop_index(
        "ix_audio_channel_patches_stockwire_product_id", table_name="audio_channel_patches"
    )
    op.drop_column("audio_channel_patches", "stockwire_product_id")

    op.drop_column("audio_channel_lists", "mixer_product_name")
    op.drop_index("ix_audio_channel_lists_mixer_product_id", table_name="audio_channel_lists")
    op.drop_column("audio_channel_lists", "mixer_product_id")
