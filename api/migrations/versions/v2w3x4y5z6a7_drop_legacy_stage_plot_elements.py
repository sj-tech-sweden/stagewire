"""drop the legacy stage_plot_elements table

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6

Plot elements live on the graph (``graph/plot_native.py``); every row was imported there
(``scripts/import_legacy_plot.py``, then a field-by-field comparison of rows and nodes showed no
difference) and nothing references the table. The links it held to channels, devices and patch
points are plain ids on the node; the sync clears one whose target is deleted, which is what the
``ON DELETE SET NULL`` foreign keys did.

This is destructive. The downgrade recreates the table **empty**: restore the pre-drop dump
(``backups/stagewire-pre-plot-elements-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: str | None = "u1v2w3x4y5z6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("stage_plot_elements")


def _link(name: str, target: str, column: str | None = None) -> sa.Column:
    return sa.Column(
        column or name,
        sa.Uuid(),
        sa.ForeignKey(f"{target}.id", ondelete="SET NULL", name=f"fk_stage_plot_elements_{name}"),
        nullable=True,
    )


def downgrade() -> None:
    op.create_table(
        "stage_plot_elements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _link("linked_channel_id", "audio_channel_patches"),
        _link("linked_patch_point_id", "channel_patch_points"),
        _link("linked_device_id", "audio_devices"),
        _link("linked_output_point_id", "output_patch_points"),
        sa.Column("linked_video_input_id", sa.Uuid(), nullable=True),
        _link("linked_lens_device_id", "audio_devices"),
        sa.Column("focal_mm", sa.Float(), nullable=True),
        sa.Column("element_type", sa.String(64), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("rotation", sa.Float(), nullable=False),
        sa.Column("width_cm", sa.Float(), nullable=False, server_default="60.0"),
        sa.Column("height_cm", sa.Float(), nullable=False, server_default="60.0"),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("image_url", sa.String(1024), nullable=False, server_default=""),
        sa.Column("coverage_angle_h", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("coverage_distance_m", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rigging_point_id", sa.Uuid(), nullable=True),
        sa.Column("power_node_id", sa.Uuid(), nullable=True),
        sa.Column("power_connector", sa.String(64), nullable=False, server_default=""),
        _link("graph_device_id", "graph_devices"),
        sa.Column("graph_link_role", sa.String(16), nullable=True),
        _link("graph_source_id", "graph_devices"),
        sa.Column("graph_source_role", sa.String(16), nullable=True),
    )
    for column in (
        "job_id",
        "graph_device_id",
        "graph_source_id",
        "power_node_id",
        "rigging_point_id",
    ):
        op.create_index(f"ix_stage_plot_elements_{column}", "stage_plot_elements", [column])
