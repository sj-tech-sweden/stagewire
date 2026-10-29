"""venue power outlet rating

Revision ID: b1c2d3e4f5g6
Revises: f7a8b9c0d1e2
Create Date: 2026-10-29 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5g6"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venue_power_outlets",
        sa.Column("rating_amps", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("venue_power_outlets", "rating_amps")
