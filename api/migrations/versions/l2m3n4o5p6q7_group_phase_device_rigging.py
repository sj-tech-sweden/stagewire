"""phase of a venue power group, rigging point on devices

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l2m3n4o5p6q7"
down_revision: str | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venue_power_groups") as batch:
        batch.add_column(sa.Column("phase", sa.String(2), nullable=True))
    with op.batch_alter_table("audio_devices") as batch:
        batch.add_column(sa.Column("rigging_point_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_audio_devices_rigging_point_id",
            "rigging_points",
            ["rigging_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_audio_devices_rigging_point_id", ["rigging_point_id"])


def downgrade() -> None:
    with op.batch_alter_table("audio_devices") as batch:
        batch.drop_index("ix_audio_devices_rigging_point_id")
        batch.drop_constraint("fk_audio_devices_rigging_point_id", type_="foreignkey")
        batch.drop_column("rigging_point_id")
    with op.batch_alter_table("venue_power_groups") as batch:
        batch.drop_column("phase")
