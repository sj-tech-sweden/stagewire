"""drop job_rental_items (replaced by per-channel/point stockwire links)

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l6m7n8o9p0q1"
down_revision: str | None = "k5l6m7n8o9p0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_table("job_rental_items")


def downgrade() -> None:
    op.create_table(
        "job_rental_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("stockwire_product_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("asset_type", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("position", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
