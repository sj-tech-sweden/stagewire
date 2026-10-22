"""stockwire requirement quantity

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-10-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "q1r2s3t4u5v6"
down_revision: str | None = "p0q1r2s3t4u5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "stockwire_requirement_links",
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    # Existing links are per slot. The next sync removes those rental requirements and
    # re-adds one requirement per product, so nothing is orphaned.


def downgrade() -> Sequence:
    op.drop_column("stockwire_requirement_links", "quantity")
