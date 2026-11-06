"""venue Standard Base Rig lives in the unified graph tables

Revision ID: z9b0c1d2e3f4
Revises: a9b8c7d6e5f4, d4e5f6a7b8c9

A venue's Standard Base Rig is the set of graph devices and connection edges that
belong to the venue itself rather than to a specific production job. We store it
in the same `graph_devices` / `graph_connection_edges` tables used by jobs so the
rig reuses the whole graph editing + cloning machinery, distinguished by `venue_id`.

`job_id` therefore becomes nullable: a base-rig row has `venue_id` set and
`job_id` NULL until it is cloned onto a job (where the clone gets `job_id` set and
`venue_id` cleared). This migration is a merge of the graph and reports heads.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z9b0c1d2e3f4"
down_revision: str | None = ("z1a2b3c4d5e6", "d4e5f6a7b8c9")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # graph_devices: job_id becomes nullable, add venue_id FK + index.
    op.alter_column("graph_devices", "job_id", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        "graph_devices",
        sa.Column(
            "venue_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_graph_devices_venue_id", "graph_devices", ["venue_id"])

    # graph_connection_edges: same shape.
    op.alter_column(
        "graph_connection_edges", "job_id", existing_type=sa.UUID(), nullable=True
    )
    op.add_column(
        "graph_connection_edges",
        sa.Column(
            "venue_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_graph_connection_edges_venue_id",
        "graph_connection_edges",
        ["venue_id"],
    )


def downgrade() -> None:
    # Drop venue-owned rows first so the NOT NULL job_id constraint can be restored.
    op.execute("DELETE FROM graph_connection_edges WHERE job_id IS NULL")
    op.execute("DELETE FROM graph_devices WHERE job_id IS NULL")

    op.drop_index("ix_graph_connection_edges_venue_id", table_name="graph_connection_edges")
    op.drop_column("graph_connection_edges", "venue_id")
    op.alter_column(
        "graph_connection_edges", "job_id", existing_type=sa.UUID(), nullable=False
    )

    op.drop_index("ix_graph_devices_venue_id", table_name="graph_devices")
    op.drop_column("graph_devices", "venue_id")
    op.alter_column("graph_devices", "job_id", existing_type=sa.UUID(), nullable=False)
