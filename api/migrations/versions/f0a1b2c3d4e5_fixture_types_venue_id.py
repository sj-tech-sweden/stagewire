"""add venue_id to fixture_types and fixture_modes

Revision ID: f0a1b2c3d4e5
Revises: b9c2d3e4f5a6
Create Date: 2026-11-05 12:00:00

Pre-existing / unrelated to the venue power work: the FixtureType and
FixtureMode ORM models declared a ``venue_id`` column, but no migration ever
added it to the underlying tables. The column is nullable (fixtures may belong
to a job instead of a venue) with a CASCADE FK to venues and a matching index,
mirroring ``job_id``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "b9c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fixture_types",
        sa.Column(
            "venue_id",
            sa.Uuid(),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_fixture_types_venue_id", "fixture_types", ["venue_id"])

    op.add_column(
        "fixture_modes",
        sa.Column(
            "venue_id",
            sa.Uuid(),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_fixture_modes_venue_id", "fixture_modes", ["venue_id"])


def downgrade() -> None:
    op.drop_index("ix_fixture_modes_venue_id", table_name="fixture_modes")
    op.drop_column("fixture_modes", "venue_id")
    op.drop_index("ix_fixture_types_venue_id", table_name="fixture_types")
    op.drop_column("fixture_types", "venue_id")
