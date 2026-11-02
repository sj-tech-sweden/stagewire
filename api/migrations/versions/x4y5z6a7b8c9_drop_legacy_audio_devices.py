"""drop the legacy audio_devices table

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8

Devices live on the graph (``graph/devices_native.py``); every row was imported there and deleted
from the table (``scripts/import_legacy_devices.py``, then a field-by-field comparison of the
pre-import dump with the nodes showed no difference, and the edges per kind were identical) and
nothing references the table any more. A device node keeps the ``audio_devices:<id>`` ref as its
identity (it is what plot links, patch points, loads and cable routes hold).

This is destructive. The downgrade recreates the table **empty**: restore the pre-drop dump
(``backups/stagewire-pre-devices-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x4y5z6a7b8c9"
down_revision: str | None = "w3x4y5z6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _refuse_if_rows(*tables: str) -> None:
    """Fail instead of dropping rows that were never imported onto the graph.

    The import (see docs/PROGRESS.md, M9 part B) moves every row to a node and deletes it, so a row
    that is still here is data this migration would lose for good.
    """
    bind = op.get_bind()
    for table in tables:
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(
                f"{table} still has rows that were not imported onto the graph; "
                "import them first (docs/PROGRESS.md, M9 part B) - dropping it would lose them"
            )


def upgrade() -> None:
    _refuse_if_rows("audio_devices")
    op.drop_table("audio_devices")


def downgrade() -> None:
    op.create_table(
        "audio_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("device_type", sa.String(64), nullable=False, server_default="other"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("ports", sa.JSON(), nullable=True),
        sa.Column("stockwire_product_id", sa.String(64), nullable=True),
        sa.Column("stockwire_product_name", sa.String(255), nullable=True),
        sa.Column("input_override", sa.Integer(), nullable=True),
        sa.Column("output_override", sa.Integer(), nullable=True),
        sa.Column("sound_list_id", sa.Uuid(), nullable=True),
        sa.Column("video_list_id", sa.Uuid(), nullable=True),
        sa.Column("sensor_width_mm", sa.Float(), nullable=True),
        sa.Column("focal_min_mm", sa.Float(), nullable=True),
        sa.Column("focal_max_mm", sa.Float(), nullable=True),
        sa.Column("max_distance_m", sa.Float(), nullable=True),
        sa.Column("throw_ratio_min", sa.Float(), nullable=True),
        sa.Column("throw_ratio_max", sa.Float(), nullable=True),
        sa.Column("image_aspect_ratio", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("power_watts", sa.Float(), nullable=True),
        sa.Column("fixture_type", sa.String(64), nullable=True),
        sa.Column("channel_mode", sa.String(64), nullable=True),
        sa.Column("footprint_channels", sa.Integer(), nullable=True),
        sa.Column("default_gel", sa.String(32), nullable=True),
        sa.Column("power_inlet", sa.String(32), nullable=False, server_default=""),
        sa.Column("power_node_id", sa.Uuid(), nullable=True),
        sa.Column("power_connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("rigging_point_id", sa.Uuid(), nullable=True),
    )
    for column in (
        "job_id",
        "power_node_id",
        "rigging_point_id",
        "sound_list_id",
        "stockwire_product_id",
        "video_list_id",
    ):
        op.create_index(f"ix_audio_devices_{column}", "audio_devices", [column])
