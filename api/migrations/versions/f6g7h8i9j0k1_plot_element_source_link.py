"""give plot elements a separate graph link for their cable source

An element can be linked to a device (its position) and to a channel, video input or output
point (its cable) at the same time, so one graph link is not enough. ``graph_device_id`` is the
device link; ``graph_source_id`` / ``graph_source_role`` are the source link.
``graph_link_role`` is no longer written and is dropped with the legacy columns.

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-10-30 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6g7h8i9j0k1"
down_revision: str | None = "e5f6g7h8i9j0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stage_plot_elements") as batch:
        batch.add_column(sa.Column("graph_source_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("graph_source_role", sa.String(length=16), nullable=True))
        batch.create_index("ix_stage_plot_elements_graph_source_id", ["graph_source_id"])
        batch.create_foreign_key(
            "fk_stage_plot_elements_graph_source_id",
            "graph_devices",
            ["graph_source_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("stage_plot_elements") as batch:
        batch.drop_constraint("fk_stage_plot_elements_graph_source_id", type_="foreignkey")
        batch.drop_index("ix_stage_plot_elements_graph_source_id")
        batch.drop_column("graph_source_role")
        batch.drop_column("graph_source_id")
