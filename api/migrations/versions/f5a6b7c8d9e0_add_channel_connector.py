"""add channel connector column

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-21

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "audio_channel_patches",
        sa.Column("connector", sa.String(length=64), nullable=True),
    )


def downgrade() -> Sequence:
    op.drop_column("audio_channel_patches", "connector")
