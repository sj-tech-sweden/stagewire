"""add stockwire requirement links

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-10-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "p0q1r2s3t4u5"
down_revision: str | None = "o9p0q1r2s3t4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.create_table(
        "stockwire_requirement_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("rental_requirement_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["production_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "item_key", name="uq_stockwire_link_job_item"),
    )
    op.create_index(
        op.f("ix_stockwire_requirement_links_job_id"),
        "stockwire_requirement_links",
        ["job_id"],
        unique=False,
    )


def downgrade() -> Sequence:
    op.drop_index(
        op.f("ix_stockwire_requirement_links_job_id"),
        table_name="stockwire_requirement_links",
    )
    op.drop_table("stockwire_requirement_links")
