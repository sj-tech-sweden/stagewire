"""add output bus mode column

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-10-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "h2i3j4k5l6m7"
down_revision: str | None = "g1h2i3j4k5l6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "channel_list_outputs",
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="mono"),
    )


def downgrade() -> Sequence:
    op.drop_column("channel_list_outputs", "mode")
