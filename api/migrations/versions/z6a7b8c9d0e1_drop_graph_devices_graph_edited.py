"""drop graph_devices.graph_edited

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0

Nothing syncs a node from rows any more (every domain is graph-native), so no node needs protecting
from the sync. The column on edges stays: an edge whose phase was set in the graph keeps it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z6a7b8c9d0e1"
down_revision: str | None = "y5z6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("graph_devices", "graph_edited")


def downgrade() -> None:
    op.add_column(
        "graph_devices",
        sa.Column("graph_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
