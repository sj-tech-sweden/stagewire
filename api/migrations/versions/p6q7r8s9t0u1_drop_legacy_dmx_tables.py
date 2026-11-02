"""drop the legacy DMX universe and step tables

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0

DMX universes, their sources and chains live on the graph (``graph/dmx_native.py``); every row of
these tables was imported there (``scripts/parity_check.py`` showed no difference first) and nothing
reads or writes them any more. ``lighting_fixtures`` and the fixture type tables stay.

This is destructive. The downgrade recreates the two tables **empty**: restore the pre-drop dump
(``backups/stagewire-pre-dmx-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p6q7r8s9t0u1"
down_revision: str | None = "o5p6q7r8s9t0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("dmx_steps")  # points at the universes
    op.drop_table("dmx_universes")


def downgrade() -> None:
    op.create_table(
        "dmx_universes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "source_device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_port", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("dmx_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
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
        sa.Column("in_port", sa.String(32), nullable=True),
        sa.Column("out_port", sa.String(32), nullable=True),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    for column in ("universe_id", "parent_id", "device_id", "fixture_id"):
        op.create_index(f"ix_dmx_steps_{column}", "dmx_steps", [column])
