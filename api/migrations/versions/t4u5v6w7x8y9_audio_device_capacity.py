"""add device input/output capacity and patch-point direction

Devices declare how many input and output ports they have (with connector
types) so the UI can show usage and warn when a box is full. Patch points gain
a direction ('in' / 'out') describing which side of a linked device they use.

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t4u5v6w7x8y9"
down_revision: str | None = "s3t4u5v6w7x8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audio_devices",
        sa.Column("input_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "audio_devices",
        sa.Column("output_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "audio_devices",
        sa.Column(
            "input_connector",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "audio_devices",
        sa.Column(
            "output_connector",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "channel_patch_points",
        sa.Column("direction", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channel_patch_points", "direction")
    op.drop_column("audio_devices", "output_connector")
    op.drop_column("audio_devices", "input_connector")
    op.drop_column("audio_devices", "output_count")
    op.drop_column("audio_devices", "input_count")
