"""devices belong to a sound channel list or a video input list

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-26 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audio_devices", sa.Column("sound_list_id", sa.Uuid(), nullable=True))
    op.add_column("audio_devices", sa.Column("video_list_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_audio_devices_sound_list_id",
        "audio_devices",
        "audio_channel_lists",
        ["sound_list_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_audio_devices_video_list_id",
        "audio_devices",
        "video_input_lists",
        ["video_list_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audio_devices_sound_list_id", "audio_devices", ["sound_list_id"])
    op.create_index("ix_audio_devices_video_list_id", "audio_devices", ["video_list_id"])


def downgrade() -> None:
    op.drop_index("ix_audio_devices_video_list_id", table_name="audio_devices")
    op.drop_index("ix_audio_devices_sound_list_id", table_name="audio_devices")
    op.drop_constraint("fk_audio_devices_video_list_id", "audio_devices", type_="foreignkey")
    op.drop_constraint("fk_audio_devices_sound_list_id", "audio_devices", type_="foreignkey")
    op.drop_column("audio_devices", "video_list_id")
    op.drop_column("audio_devices", "sound_list_id")
