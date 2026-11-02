"""add optimistic revisions to audio patch records

Revision ID: b2c3d4e5f6g7
Revises: a9f8e7d6c5b4
Create Date: 2026-10-29 15:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6g7"
down_revision: str | None = "a9f8e7d6c5b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in (
        "audio_channel_patches",
        "channel_patch_points",
        "channel_list_outputs",
        "output_patch_points",
    ):
        op.add_column(
            table,
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        )


def downgrade() -> None:
    for table in (
        "output_patch_points",
        "channel_list_outputs",
        "channel_patch_points",
        "audio_channel_patches",
    ):
        op.drop_column(table, "revision")
