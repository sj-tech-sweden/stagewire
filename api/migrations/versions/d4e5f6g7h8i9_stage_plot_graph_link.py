"""link stage plot elements to graph devices

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-10-30 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6g7h8i9"
down_revision: str | None = "c3d4e5f6g7h8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stage_plot_elements") as batch:
        batch.add_column(sa.Column("graph_device_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("graph_link_role", sa.String(length=16), nullable=True))
        batch.create_index("ix_stage_plot_elements_graph_device_id", ["graph_device_id"])
        batch.create_foreign_key(
            "fk_stage_plot_elements_graph_device_id",
            "graph_devices",
            ["graph_device_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("stage_plot_elements") as batch:
        batch.drop_constraint("fk_stage_plot_elements_graph_device_id", type_="foreignkey")
        batch.drop_index("ix_stage_plot_elements_graph_device_id")
        batch.drop_column("graph_link_role")
        batch.drop_column("graph_device_id")
