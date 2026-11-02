"""drop the legacy lighting_fixtures table

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5

Fixtures live on the graph (``graph/fixtures_native.py``); every row was imported there
(``scripts/parity_check.py`` showed no difference first) and nothing references the table: the DMX
steps that named fixtures went with ``p6q7r8s9t0u1``, and the load links are attributes of the
fixture. The fixture type and mode tables stay.

This is destructive. The downgrade recreates the table **empty**: restore the pre-drop dump
(``backups/stagewire-pre-fixtures-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: str | None = "t0u1v2w3x4y5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("lighting_fixtures")


def downgrade() -> None:
    op.create_table(
        "lighting_fixtures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("universe", sa.Integer(), nullable=True),
        sa.Column("dmx_address", sa.Integer(), nullable=True),
        sa.Column("fixture_type", sa.String(64), nullable=True),
        sa.Column("channel_mode", sa.String(64), nullable=True),
        sa.Column("footprint", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("gel", sa.String(32), nullable=True),
        sa.Column("purpose", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column(
            "fixture_type_id",
            sa.Uuid(),
            sa.ForeignKey("fixture_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fixture_mode_id",
            sa.Uuid(),
            sa.ForeignKey("fixture_modes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rigging_point_id", sa.Uuid(), nullable=True),
        sa.Column("power_node_id", sa.Uuid(), nullable=True),
        sa.Column("power_connector", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in (
        "job_id",
        "device_id",
        "import_batch_id",
        "fixture_type_id",
        "fixture_mode_id",
        "rigging_point_id",
        "power_node_id",
    ):
        op.create_index(f"ix_lighting_fixtures_{column}", "lighting_fixtures", [column])
