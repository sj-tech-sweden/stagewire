"""drop the legacy channel list tables

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7

Channel lists, channels, outputs and their patch points live on the graph
(``graph/audio_native.py``); every row was imported there and deleted from these tables
(``scripts/import_legacy_audio.py``, then a field-by-field comparison of the pre-import dump with
the nodes showed no difference) and nothing references them any more. ``audio_devices.sound_list_id``
becomes a plain id holding the list's public id (a list made in the graph has no row here); deleting
a list clears it in code, as the foreign key's ``ON DELETE SET NULL`` did.

This is destructive. The downgrade recreates the tables **empty**: restore the pre-drop dump
(``backups/stagewire-pre-audio-lists-drop-*.dump``) to get the old rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "w3x4y5z6a7b8"
down_revision: str | None = "v2w3x4y5z6a7"
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
    _refuse_if_rows(
        "audio_channel_lists",
        "audio_channel_patches",
        "channel_list_outputs",
        "channel_patch_points",
        "output_patch_points",
    )
    op.drop_constraint("fk_audio_devices_sound_list_id", "audio_devices", type_="foreignkey")
    op.drop_table("output_patch_points")
    op.drop_table("channel_patch_points")
    op.drop_table("channel_list_outputs")
    op.drop_table("audio_channel_patches")
    op.drop_table("audio_channel_lists")


def _fk(column: str, target: str, ondelete: str, name: str | None = None) -> sa.Column:
    return sa.Column(
        column,
        sa.Uuid(),
        sa.ForeignKey(f"{target}.id", ondelete=ondelete, name=name),
        nullable=ondelete == "SET NULL",
    )


def downgrade() -> None:
    op.create_table(
        "audio_channel_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("mixer_product_id", sa.String(64), nullable=True),
        sa.Column("mixer_product_name", sa.String(255), nullable=True),
        sa.Column("mixer_inputs", sa.Integer(), nullable=True),
        sa.Column("mixer_buses", sa.Integer(), nullable=True),
    )
    op.create_index("ix_audio_channel_lists_job_id", "audio_channel_lists", ["job_id"])
    op.create_index(
        "ix_audio_channel_lists_mixer_product_id", "audio_channel_lists", ["mixer_product_id"]
    )
    op.create_foreign_key(
        "fk_audio_devices_sound_list_id",
        "audio_devices",
        "audio_channel_lists",
        ["sound_list_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "audio_channel_patches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("channel_list_id", "audio_channel_lists", "CASCADE", "fk_audio_channel_patches_channel_list_id"),
        sa.Column("channel_number", sa.Integer(), nullable=False),
        sa.Column("source_label", sa.String(255), nullable=False),
        sa.Column("input_type", sa.String(64), nullable=True),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("device", sa.String(255), nullable=True),
        sa.Column("stand_type", sa.String(255), nullable=False),
        sa.Column("instrument_group", sa.String(32), nullable=False, server_default="other"),
        sa.Column("performer_name", sa.String(255), nullable=True),
        sa.Column("wireless_pack", sa.String(255), nullable=True),
        sa.Column("wireless_frequency", sa.String(64), nullable=True),
        sa.Column("phantom_power", sa.Boolean(), nullable=False),
        sa.Column("stereo", sa.Boolean(), nullable=False),
        sa.Column("stereo_channel", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("color_code", sa.String(32), nullable=True),
        sa.Column("stockwire_asset_id", sa.String(255), nullable=True),
        sa.Column("stockwire_product_id", sa.String(64), nullable=True),
        sa.Column("stockwire_product_name", sa.String(255), nullable=True),
        sa.Column("stand_product_id", sa.String(64), nullable=True),
        sa.Column("stand_product_name", sa.String(255), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_audio_channel_patches_stockwire_product_id",
        "audio_channel_patches",
        ["stockwire_product_id"],
    )
    op.create_index(
        "ix_audio_channel_patches_stand_product_id", "audio_channel_patches", ["stand_product_id"]
    )
    op.create_table(
        "channel_list_outputs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "channel_list_id",
            sa.Uuid(),
            sa.ForeignKey("audio_channel_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default="Output"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("color_code", sa.String(32), nullable=True),
        sa.Column("mode", sa.String(32), nullable=False, server_default="mono"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_channel_list_outputs_channel_list_id", "channel_list_outputs", ["channel_list_id"]
    )
    op.create_table(
        "channel_patch_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "channel_id",
            sa.Uuid(),
            sa.ForeignKey("audio_channel_patches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("point_type", sa.String(64), nullable=False, server_default="mixer"),
        sa.Column("connector", sa.String(64), nullable=False, server_default=""),
        sa.Column("patch_label", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.String(2000), nullable=False, server_default=""),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_channel_patch_points_channel_id", "channel_patch_points", ["channel_id"])
    op.create_index("ix_channel_patch_points_device_id", "channel_patch_points", ["device_id"])
    op.create_table(
        "output_patch_points",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "output_id",
            sa.Uuid(),
            sa.ForeignKey("channel_list_outputs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("point_type", sa.String(64), nullable=False, server_default="mixer"),
        sa.Column("connector", sa.String(64), nullable=True),
        sa.Column("patch_label", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("parallel", sa.Boolean(), nullable=False, server_default=sa.false()),
        _fk("parent_id", "output_patch_points", "SET NULL", "fk_output_patch_points_parent_id"),
        sa.Column("bus_connector", sa.String(32), nullable=True),
        _fk("device_id", "audio_devices", "SET NULL", "fk_output_patch_points_device_id"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_output_patch_points_device_id", "output_patch_points", ["device_id"])
    op.create_index("ix_output_patch_points_output_id", "output_patch_points", ["output_id"])
