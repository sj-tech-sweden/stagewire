"""add report locales and freeform layouts

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-26 08:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_templates",
        sa.Column("locale", sa.String(length=8), server_default="en", nullable=False),
    )
    op.add_column("report_templates", sa.Column("layout_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_templates", "layout_json")
    op.drop_column("report_templates", "locale")
