"""DMX chains per universe and power chains per fixture

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-30 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fixture_types",
        sa.Column("category", sa.String(64), nullable=False, server_default=""),
    )
    op.create_table(
        "dmx_universes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "source_device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_port", sa.String(32), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_dmx_universes_job_id", "dmx_universes", ["job_id"])
    op.create_index("ix_dmx_universes_source_device_id", "dmx_universes", ["source_device_id"])
    op.create_table(
        "dmx_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "universe_id",
            sa.Uuid(),
            sa.ForeignKey("dmx_universes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("dmx_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fixture_id",
            sa.Uuid(),
            sa.ForeignKey("lighting_fixtures.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("in_port", sa.String(32), nullable=False, server_default=""),
        sa.Column("out_port", sa.String(32), nullable=False, server_default=""),
        sa.Column("connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_dmx_steps_universe_id", "dmx_steps", ["universe_id"])
    op.create_index("ix_dmx_steps_parent_id", "dmx_steps", ["parent_id"])
    op.create_index("ix_dmx_steps_device_id", "dmx_steps", ["device_id"])
    op.create_index("ix_dmx_steps_fixture_id", "dmx_steps", ["fixture_id"])
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
    op.create_index("ix_power_steps_fixture_id", "power_steps", ["fixture_id"])
    op.create_index("ix_power_steps_device_id", "power_steps", ["device_id"])


def downgrade() -> None:
    op.drop_table("power_steps")
    op.drop_table("dmx_steps")
    op.drop_table("dmx_universes")
    op.drop_column("fixture_types", "category")
