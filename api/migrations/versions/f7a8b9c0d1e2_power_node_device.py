"""a power node can stand for a device on the plot, so power cables can be drawn

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-31 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("power_nodes", sa.Column("device_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_power_nodes_device_id",
        "power_nodes",
        "audio_devices",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_power_nodes_device_id", "power_nodes", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_power_nodes_device_id", table_name="power_nodes")
    op.drop_constraint("fk_power_nodes_device_id", "power_nodes", type_="foreignkey")
    op.drop_column("power_nodes", "device_id")
