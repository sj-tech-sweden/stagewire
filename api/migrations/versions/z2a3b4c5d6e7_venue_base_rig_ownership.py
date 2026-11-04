"""venue base rig ownership

Make every job-owned device model venue-ownable so a venue can store a
Standard Base Rig (its own devices/patch) that is cloned onto a job when the
venue is assigned.

Revision ID: z2a3b4c5d6e7
Revises: z1a2b3c4d5e6
Create Date: 2026-11-04 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z2a3b4c5d6e7"
down_revision: str | None = "z1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every job-owned device model gets a venue_id so a venue can own a base rig.
TABLES = [
    "audio_channel_lists",
    "audio_devices",
    "stage_plot_elements",
    "audio_channel_patches",
    "channel_patch_points",
    "channel_list_outputs",
    "output_patch_points",
    "stockwire_requirement_links",
    "video_input_lists",
    "video_inputs",
    "video_patch_points",
    "video_outputs",
    "video_output_patch_points",
    "lighting_fixtures",
    "fixture_types",
    "dmx_universes",
    "fixture_modes",
    "dmx_steps",
    "rigging_points",
    "power_nodes",
    "power_node_feeds",
]

# Root tables own their rows directly via job_id; venue-owned base-rig rows set
# job_id to NULL, so the column must be nullable for them.
ROOT_TABLES = [
    "audio_channel_lists",
    "audio_devices",
    "stage_plot_elements",
    "stockwire_requirement_links",
    "video_input_lists",
    "lighting_fixtures",
    "fixture_types",
    "dmx_universes",
    "rigging_points",
    "power_nodes",
    "power_node_feeds",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "venue_id",
                sa.Uuid(),
                sa.ForeignKey("venues.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{table}_venue_id", table, ["venue_id"])
    for table in ROOT_TABLES:
        op.alter_column(
            table,
            "job_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    for table in reversed(ROOT_TABLES):
        op.alter_column(
            table,
            "job_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_venue_id", table)
        op.drop_column(table, "venue_id")
