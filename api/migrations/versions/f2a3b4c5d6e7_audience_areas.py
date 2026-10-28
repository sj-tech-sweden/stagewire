"""audience areas on venues and jobs

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-27 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "venues",
        sa.Column("audience_polygon", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "production_jobs",
        sa.Column("audience_polygon", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("production_jobs", "audience_polygon")
    op.drop_column("venues", "audience_polygon")
