"""add mixer io to channel lists

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-10-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "o9p0q1r2s3t4"
down_revision: str | None = "n8o9p0q1r2s3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "audio_channel_lists",
        sa.Column("mixer_inputs", sa.Integer(), nullable=True),
    )
    op.add_column(
        "audio_channel_lists",
        sa.Column("mixer_buses", sa.Integer(), nullable=True),
    )


def downgrade() -> Sequence:
    op.drop_column("audio_channel_lists", "mixer_buses")
    op.drop_column("audio_channel_lists", "mixer_inputs")
