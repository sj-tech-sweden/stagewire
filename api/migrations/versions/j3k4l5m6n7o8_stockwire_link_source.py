"""record provenance on stockwire requirement links

Revision ID: j3k4l5m6n7o8
Revises: i3s4t5u6v7w8
Create Date: 2026-11-28

Links already in the database were all written by the sync, so they are backfilled
as ``sync``. The explicit "request to add" flow now writes its own links with
``source='request'``; those are recorded for traceability but must never be
deleted by the product-level reconciliation ("only remove what Stagewire added
and then removed again").
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j3k4l5m6n7o8"
down_revision: str | None = "i3s4t5u6v7w8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "stockwire_requirement_links",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="sync"),
    )


def downgrade() -> Sequence:
    op.drop_column("stockwire_requirement_links", "source")
