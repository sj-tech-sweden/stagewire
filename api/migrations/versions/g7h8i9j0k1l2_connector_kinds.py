"""connector kinds

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g7h8i9j0k1l2"
down_revision: str | None = "f6g7h8i9j0k1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_kinds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_connector_kinds_key", "connector_kinds", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_connector_kinds_key", table_name="connector_kinds")
    op.drop_table("connector_kinds")
