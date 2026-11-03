"""add production_job start_date / end_date

Revision ID: a9b8c7d6e5f4
Revises: z8a9b0c1d2e3

Adds the inclusive rental date range (``start_date`` / ``end_date``) used by the Stockwire
availability check, chained off the wireless-workbench head that the deployed database is
already stamped at.

The upstream Stockwire availability endpoint takes ``string($date)`` bounds, so these are
plain ``Date`` columns (no time component), not the ``DateTime`` already used for event_date.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "z8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("production_jobs", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("production_jobs", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("production_jobs", "end_date")
    op.drop_column("production_jobs", "start_date")
