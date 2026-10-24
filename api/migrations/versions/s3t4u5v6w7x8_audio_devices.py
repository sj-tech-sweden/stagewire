"""add audio devices grouping patch points into physical boxes

A device (stagebox, mixer, split, etc.) groups every patch point that belongs
to one physical unit, so a stage-plot element can be linked to the whole box
instead of a single connector, and the On-stage column can resolve to every
channel of that box.

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s3t4u5v6w7x8"
down_revision: str | None = "r2s3t4u5v6w7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audio_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "device_type",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'other'"),
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audio_devices_job_id", "audio_devices", ["job_id"])

    op.add_column(
        "channel_patch_points",
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_channel_patch_points_device_id", "channel_patch_points", ["device_id"]
    )

    op.add_column(
        "stage_plot_elements",
        sa.Column(
            "linked_device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("stage_plot_elements", "linked_device_id")
    op.drop_index("ix_channel_patch_points_device_id", table_name="channel_patch_points")
    op.drop_column("channel_patch_points", "device_id")
    op.drop_index("ix_audio_devices_job_id", table_name="audio_devices")
    op.drop_table("audio_devices")
