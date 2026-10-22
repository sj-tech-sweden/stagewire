"""add parallel flag to output patch points

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-10-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "i3j4k5l6m7n8"
down_revision: str | None = "h2i3j4k5l6m7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "output_patch_points",
        sa.Column("parallel", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> Sequence:
    op.drop_column("output_patch_points", "parallel")
