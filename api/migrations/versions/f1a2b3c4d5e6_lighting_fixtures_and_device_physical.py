"""lighting fixture patch and device weight, power and fixture profile

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-10-29 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audio_devices", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.add_column("audio_devices", sa.Column("power_watts", sa.Float(), nullable=True))
    op.add_column("audio_devices", sa.Column("fixture_type", sa.String(64), nullable=True))
    op.add_column("audio_devices", sa.Column("channel_mode", sa.String(64), nullable=True))
    op.add_column("audio_devices", sa.Column("footprint_channels", sa.Integer(), nullable=True))
    op.add_column("audio_devices", sa.Column("default_gel", sa.String(32), nullable=True))
    op.create_table(
        "lighting_fixtures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("audio_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("universe", sa.Integer(), nullable=True),
        sa.Column("dmx_address", sa.Integer(), nullable=True),
        sa.Column("fixture_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("channel_mode", sa.String(64), nullable=False, server_default=""),
        sa.Column("footprint", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(255), nullable=False, server_default=""),
        sa.Column("gel", sa.String(32), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lighting_fixtures_job_id", "lighting_fixtures", ["job_id"])
    op.create_index("ix_lighting_fixtures_device_id", "lighting_fixtures", ["device_id"])
    op.create_index("ix_lighting_fixtures_import_batch_id", "lighting_fixtures", ["import_batch_id"])


def downgrade() -> None:
    op.drop_table("lighting_fixtures")
    for column in (
        "default_gel",
        "footprint_channels",
        "channel_mode",
        "fixture_type",
        "power_watts",
        "weight_kg",
    ):
        op.drop_column("audio_devices", column)
