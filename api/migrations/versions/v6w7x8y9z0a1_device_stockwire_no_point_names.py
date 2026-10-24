"""device-level stockwire products; patch point names removed; output points linked to devices

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-10-24 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v6w7x8y9z0a1"
down_revision: str | None = "u5v6w7x8y9z0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audio_devices", sa.Column("stockwire_product_id", sa.String(64), nullable=True))
    op.add_column("audio_devices", sa.Column("stockwire_product_name", sa.String(255), nullable=True))
    op.create_index(
        "ix_audio_devices_stockwire_product_id", "audio_devices", ["stockwire_product_id"]
    )
    op.execute(
        """
        UPDATE audio_devices d
        SET stockwire_product_id = s.pid, stockwire_product_name = s.pname
        FROM (
            SELECT DISTINCT ON (device_id) device_id,
                   stockwire_product_id AS pid, stockwire_product_name AS pname
            FROM channel_patch_points
            WHERE device_id IS NOT NULL AND stockwire_product_id IS NOT NULL
            ORDER BY device_id
        ) s
        WHERE d.id = s.device_id AND d.stockwire_product_id IS NULL
        """
    )

    op.add_column("output_patch_points", sa.Column("device_id", sa.Uuid(), nullable=True))
    op.create_index("ix_output_patch_points_device_id", "output_patch_points", ["device_id"])
    op.create_foreign_key(
        "fk_output_patch_points_device_id",
        "output_patch_points",
        "audio_devices",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE audio_devices d
        SET stockwire_product_id = s.pid, stockwire_product_name = s.pname
        FROM (
            SELECT DISTINCT ON (device_id) device_id,
                   stockwire_product_id AS pid, stockwire_product_name AS pname
            FROM output_patch_points
            WHERE device_id IS NOT NULL AND stockwire_product_id IS NOT NULL
            ORDER BY device_id
        ) s
        WHERE d.id = s.device_id AND d.stockwire_product_id IS NULL
        """
    )

    op.drop_index("ix_channel_patch_points_stockwire_product_id", table_name="channel_patch_points")
    op.drop_column("channel_patch_points", "stockwire_product_id")
    op.drop_column("channel_patch_points", "stockwire_product_name")
    op.drop_column("channel_patch_points", "name")

    op.drop_index("ix_output_patch_points_stockwire_product_id", table_name="output_patch_points")
    op.drop_column("output_patch_points", "stockwire_product_id")
    op.drop_column("output_patch_points", "stockwire_product_name")
    op.drop_column("output_patch_points", "name")


def downgrade() -> None:
    op.add_column(
        "output_patch_points",
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column("output_patch_points", sa.Column("stockwire_product_name", sa.String(255), nullable=True))
    op.add_column("output_patch_points", sa.Column("stockwire_product_id", sa.String(64), nullable=True))
    op.create_index(
        "ix_output_patch_points_stockwire_product_id", "output_patch_points", ["stockwire_product_id"]
    )
    op.drop_constraint("fk_output_patch_points_device_id", "output_patch_points", type_="foreignkey")
    op.drop_index("ix_output_patch_points_device_id", table_name="output_patch_points")
    op.drop_column("output_patch_points", "device_id")

    op.add_column(
        "channel_patch_points",
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column("channel_patch_points", sa.Column("stockwire_product_name", sa.String(255), nullable=True))
    op.add_column("channel_patch_points", sa.Column("stockwire_product_id", sa.String(64), nullable=True))
    op.create_index(
        "ix_channel_patch_points_stockwire_product_id", "channel_patch_points", ["stockwire_product_id"]
    )

    op.drop_index("ix_audio_devices_stockwire_product_id", table_name="audio_devices")
    op.drop_column("audio_devices", "stockwire_product_name")
    op.drop_column("audio_devices", "stockwire_product_id")
