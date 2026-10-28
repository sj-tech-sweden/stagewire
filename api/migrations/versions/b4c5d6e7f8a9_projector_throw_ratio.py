"""projector throw ratio on devices

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-28 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audio_devices", sa.Column("throw_ratio_min", sa.Float(), nullable=True))
    op.add_column("audio_devices", sa.Column("throw_ratio_max", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("audio_devices", "throw_ratio_max")
    op.drop_column("audio_devices", "throw_ratio_min")
