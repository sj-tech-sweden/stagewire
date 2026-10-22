"""add stockwire product link columns to output patch points

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n8o9p0q1r2s3"
down_revision: str | None = "m7n8o9p0q1r2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "output_patch_points",
        sa.Column("stockwire_product_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_output_patch_points_stockwire_product_id",
        "output_patch_points",
        ["stockwire_product_id"],
    )
    op.add_column(
        "output_patch_points",
        sa.Column("stockwire_product_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("output_patch_points", "stockwire_product_name")
    op.drop_index(
        "ix_output_patch_points_stockwire_product_id", table_name="output_patch_points"
    )
    op.drop_column("output_patch_points", "stockwire_product_id")
