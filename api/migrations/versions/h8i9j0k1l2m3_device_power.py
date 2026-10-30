"""power inlet and power node plug on devices

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: str | None = "g7h8i9j0k1l2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audio_devices") as batch:
        batch.add_column(sa.Column("power_inlet", sa.String(32), nullable=False, server_default=""))
        batch.add_column(sa.Column("power_node_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("power_connector", sa.String(64), nullable=False, server_default="")
        )
        batch.create_foreign_key(
            "fk_audio_devices_power_node_id",
            "power_nodes",
            ["power_node_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_audio_devices_power_node_id", ["power_node_id"])


def downgrade() -> None:
    with op.batch_alter_table("audio_devices") as batch:
        batch.drop_index("ix_audio_devices_power_node_id")
        batch.drop_constraint("fk_audio_devices_power_node_id", type_="foreignkey")
        batch.drop_column("power_connector")
        batch.drop_column("power_node_id")
        batch.drop_column("power_inlet")
