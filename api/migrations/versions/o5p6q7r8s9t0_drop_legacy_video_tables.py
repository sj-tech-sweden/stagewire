"""drop the legacy video tables

Revision ID: o5p6q7r8s9t0
Revises: m3n4o5p6q7r8

Video lists, inputs, outputs and their patch points live on the graph (``graph_devices`` /
``graph_connection_edges``, see ``graph/video_native.py``); every row of these tables was imported
there (``scripts/parity_check.py`` showed no difference before this revision was written) and
nothing reads or writes them any more.

This is destructive. The downgrade recreates the five tables **empty**: the data is not copied
back, so restore the pre-drop dump (``backups/stagewire-pre-video-drop-*.dump``) to get the old
rows. ``audio_devices.video_list_id`` and ``stage_plot_elements.linked_video_input_id`` already
lost their foreign keys in ``m3n4o5p6q7r8``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o5p6q7r8s9t0"
down_revision: str | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # children first: the foreign keys point from the points to the rows to the lists
    for table in (
        "video_output_patch_points",
        "video_outputs",
        "video_patch_points",
        "video_inputs",
        "video_input_lists",
    ):
        op.drop_table(table)


def downgrade() -> None:
    op.create_table(
        "video_input_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("switcher_product_id", sa.String(64), nullable=True),
        sa.Column("switcher_product_name", sa.String(255), nullable=True),
        sa.Column("switcher_inputs", sa.Integer(), nullable=True),
        sa.Column("switcher_outputs", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_video_input_lists_job_id", "video_input_lists", ["job_id"])
    op.create_table(
        "video_inputs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "list_id",
            sa.Uuid(),
            sa.ForeignKey("video_input_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_number", sa.Integer(), nullable=False),
        sa.Column("source_label", sa.String(255), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("stockwire_product_id", sa.String(64), nullable=True),
        sa.Column("stockwire_product_name", sa.String(255), nullable=True),
    )
    op.create_index("ix_video_inputs_list_id", "video_inputs", ["list_id"])
    op.create_table(
        "video_patch_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "input_id",
            sa.Uuid(),
            sa.ForeignKey("video_inputs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("patch_label", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("source_port", sa.String(32), nullable=True),
        sa.Column("input_port", sa.String(32), nullable=True),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_video_patch_points_input_id", "video_patch_points", ["input_id"])
    op.create_index("ix_video_patch_points_device_id", "video_patch_points", ["device_id"])
    op.create_table(
        "video_outputs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "list_id",
            sa.Uuid(),
            sa.ForeignKey("video_input_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("output_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("destination_label", sa.String(255), nullable=True),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
    )
    op.create_index("ix_video_outputs_list_id", "video_outputs", ["list_id"])
    op.create_table(
        "video_output_patch_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "output_id",
            sa.Uuid(),
            sa.ForeignKey("video_outputs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("patch_label", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("source_port", sa.String(32), nullable=True),
        sa.Column("input_port", sa.String(32), nullable=True),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("video_output_patch_points.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_video_output_patch_points_output_id", "video_output_patch_points", ["output_id"]
    )
    op.create_index(
        "ix_video_output_patch_points_parent_id", "video_output_patch_points", ["parent_id"]
    )
    op.create_index(
        "ix_video_output_patch_points_device_id", "video_output_patch_points", ["device_id"]
    )
