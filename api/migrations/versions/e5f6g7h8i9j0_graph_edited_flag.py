"""track graph rows edited in the graph so legacy sync leaves them alone

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-10-30 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6g7h8i9j0"
down_revision: str | None = "d4e5f6g7h8i9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("graph_devices", "graph_connection_edges"):
        op.add_column(
            table,
            sa.Column("graph_edited", sa.Boolean(), server_default=sa.false(), nullable=False),
        )


def downgrade() -> None:
    for table in ("graph_connection_edges", "graph_devices"):
        op.drop_column(table, "graph_edited")
