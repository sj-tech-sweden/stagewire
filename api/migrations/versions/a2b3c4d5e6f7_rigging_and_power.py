"""rigging points, power distros and circuits; load assignments on fixtures and plot elements

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rigging_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trim_height_cm", sa.Float(), nullable=True),
        sa.Column("weight_capacity_kg", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_rigging_points_job_id", "rigging_points", ["job_id"])
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
        sa.Column("phase", sa.String(4), nullable=False, server_default="L1"),
        sa.Column("breaker_amps", sa.Float(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_power_circuits_distro_id", "power_circuits", ["distro_id"])
    for table in ("lighting_fixtures", "stage_plot_elements"):
        op.add_column(table, sa.Column("rigging_point_id", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("power_circuit_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_rigging_point_id",
            table,
            "rigging_points",
            ["rigging_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table}_power_circuit_id",
            table,
            "power_circuits",
            ["power_circuit_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_rigging_point_id", table, ["rigging_point_id"])
        op.create_index(f"ix_{table}_power_circuit_id", table, ["power_circuit_id"])


def downgrade() -> None:
    for table in ("stage_plot_elements", "lighting_fixtures"):
        op.drop_index(f"ix_{table}_power_circuit_id", table_name=table)
        op.drop_index(f"ix_{table}_rigging_point_id", table_name=table)
        op.drop_constraint(f"fk_{table}_power_circuit_id", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_rigging_point_id", table, type_="foreignkey")
        op.drop_column(table, "power_circuit_id")
        op.drop_column(table, "rigging_point_id")
    op.drop_table("power_circuits")
    op.drop_table("power_distros")
    op.drop_table("rigging_points")
