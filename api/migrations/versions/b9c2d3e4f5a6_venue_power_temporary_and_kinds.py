"""temporary flag on venue power groups; widen kind to generator/breakout

Revision ID: b9c2d3e4f5a6
Revises: a0b1c2d3e4f5

Extends the venue supply tree so it can model temporary equipment and a second supply:

- ``temporary`` flags hired gear (generators, breakout distros, cables) that is not part of the
  venue's permanent install.
- ``kind`` already accepts 'incoming' | 'panel' | 'group'; this migration only widens the column's
  *meaning* (the String(16) already holds 'generator'/'breakout'). No data fixup is needed: the
  backfill in a0b1c2d3e4f5 set every existing node to one of the three base kinds, and the new
  kinds are only created by the API going forward.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9c2d3e4f5a6"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venue_power_groups",
        sa.Column("temporary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("venue_power_groups", "temporary")
