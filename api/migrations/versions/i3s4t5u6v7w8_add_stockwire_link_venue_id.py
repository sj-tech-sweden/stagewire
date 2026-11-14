"""add venue_id to stockwire requirement links

Revision ID: i3s4t5u6v7w8
Revises: h2i3s4t5o6r7
Create Date: 2026-11-14

The ``StockwireRequirementLink`` model gained a ``venue_id`` column when venues
became template jobs / base rigs (commit 3d19061), mirroring the same column on
graph devices, but the migration that created this table (p0q1r2s3t4u5) never
added it and no later migration did either. The sync endpoint's first query
(``SELECT ... FROM stockwire_requirement_links``) then 500s with
``UndefinedColumn: column stockwire_requirement_links.venue_id does not exist``,
which surfaced in the UI as a "Network Error". This brings the table in line
with the model: a nullable CASCADE FK so a link can belong to either a job or a
venue base rig, plus a matching index.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i3s4t5u6v7w8"
down_revision: str | None = "h2i3s4t5o6r7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> Sequence:
    op.add_column(
        "stockwire_requirement_links",
        sa.Column(
            "venue_id",
            sa.Uuid(),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_stockwire_requirement_links_venue_id"),
        "stockwire_requirement_links",
        ["venue_id"],
        unique=False,
    )


def downgrade() -> Sequence:
    op.drop_index(
        op.f("ix_stockwire_requirement_links_venue_id"),
        table_name="stockwire_requirement_links",
    )
    op.drop_column("stockwire_requirement_links", "venue_id")
