"""device input and output count overrides

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-10-25 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z0a1b2c3d4e5"
down_revision: str | None = "y9z0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audio_devices", sa.Column("input_override", sa.Integer(), nullable=True))
    op.add_column("audio_devices", sa.Column("output_override", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("audio_devices", "output_override")
    op.drop_column("audio_devices", "input_override")
