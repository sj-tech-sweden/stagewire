"""add instrument grouping and wireless input details

Revision ID: a7b8c9d0e1f2
Revises: z0a1b2c3d4e5
Create Date: 2026-11-02 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | tuple[str, str] | None = (
    "z0a1b2c3d4e5",
    "d4e5f6a7b8c9",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE audio_channel_patches "
        "SET device = transducer "
        "WHERE (device IS NULL OR device = '') AND transducer IS NOT NULL AND transducer != ''"
    )
    op.drop_column("audio_channel_patches", "transducer")
    op.add_column(
        "audio_channel_patches",
        sa.Column("instrument_group", sa.String(length=32), server_default="other", nullable=False),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("performer_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("wireless_pack", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "audio_channel_patches",
        sa.Column("wireless_frequency", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audio_channel_patches", "wireless_frequency")
    op.drop_column("audio_channel_patches", "wireless_pack")
    op.drop_column("audio_channel_patches", "performer_name")
    op.drop_column("audio_channel_patches", "instrument_group")
    op.add_column(
        "audio_channel_patches",
        sa.Column("transducer", sa.String(length=255), server_default="", nullable=False),
    )
    op.execute(
        "UPDATE audio_channel_patches SET transducer = device "
        "WHERE device IS NOT NULL AND device != ''"
    )
