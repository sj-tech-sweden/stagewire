"""power tree replaces distros and circuits; venue power outlets

The tree is power_nodes: a source (mains or a venue outlet), distros and breakouts, each with
outputs. Fixtures and plot elements plug into a node's output. Distros, circuits and the
per-fixture power steps are removed; their rows are not converted (dev data only).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-31 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_power_outlets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "venue_id", sa.Uuid(), sa.ForeignKey("venues.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("x_cm", sa.Float(), nullable=True),
        sa.Column("y_cm", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_venue_power_outlets_venue_id", "venue_power_outlets", ["venue_id"])
    op.create_table(
        "power_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("power_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(16), nullable=False, server_default="distro"),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("feed_connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("phase", sa.String(4), nullable=True),
        sa.Column("outputs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rating_amps", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "venue_outlet_id",
            sa.Uuid(),
            sa.ForeignKey("venue_power_outlets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_power_nodes_job_id", "power_nodes", ["job_id"])
    op.create_index("ix_power_nodes_parent_id", "power_nodes", ["parent_id"])
    op.create_index("ix_power_nodes_venue_outlet_id", "power_nodes", ["venue_outlet_id"])

    op.drop_table("power_steps")
    for table in ("lighting_fixtures", "stage_plot_elements"):
        op.drop_column(table, "power_circuit_id")
        op.add_column(table, sa.Column("power_node_id", sa.Uuid(), nullable=True))
        op.add_column(
            table,
            sa.Column("power_connector", sa.String(64), nullable=False, server_default=""),
        )
        op.create_foreign_key(
            f"fk_{table}_power_node_id",
            table,
            "power_nodes",
            ["power_node_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_power_node_id", table, ["power_node_id"])
    op.drop_table("power_circuits")
    op.drop_table("power_distros")


def downgrade() -> None:
    op.create_table(
        "power_distros",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voltage", sa.Integer(), nullable=False, server_default="230"),
        sa.Column("amps_per_phase", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_power_distros_job_id", "power_distros", ["job_id"])
    op.create_table(
        "power_circuits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "distro_id",
            sa.Uuid(),
            sa.ForeignKey("power_distros.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("phases", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("phase", sa.String(4), nullable=True),
        sa.Column("breaker_amps", sa.Float(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_power_circuits_distro_id", "power_circuits", ["distro_id"])
    for table in ("stage_plot_elements", "lighting_fixtures"):
        op.drop_index(f"ix_{table}_power_node_id", table_name=table)
        op.drop_constraint(f"fk_{table}_power_node_id", table, type_="foreignkey")
        op.drop_column(table, "power_connector")
        op.drop_column(table, "power_node_id")
        op.add_column(table, sa.Column("power_circuit_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_power_circuit_id",
            table,
            "power_circuits",
            ["power_circuit_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_table(
        "power_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "fixture_id",
            sa.Uuid(),
            sa.ForeignKey("lighting_fixtures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("connector_in", sa.String(64), nullable=False, server_default=""),
        sa.Column("connector_out", sa.String(64), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.drop_index("ix_power_nodes_venue_outlet_id", table_name="power_nodes")
    op.drop_index("ix_power_nodes_parent_id", table_name="power_nodes")
    op.drop_index("ix_power_nodes_job_id", table_name="power_nodes")
    op.drop_table("power_nodes")
    op.drop_index("ix_venue_power_outlets_venue_id", table_name="venue_power_outlets")
    op.drop_table("venue_power_outlets")
