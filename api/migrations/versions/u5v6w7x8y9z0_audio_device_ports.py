"""replace device capacity columns with granular port groups

Devices now describe capacity as a list of port groups (direction + connector +
count), e.g. 4 XLR in, 4 TRS in, 8 XLR out. The flat input_count/output_count/
connector columns are dropped and a JSON `ports` column holds the groups. The
stored `direction` on patch points is no longer needed because in/out is derived
from chain position, so that column is dropped too.

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u5v6w7x8y9z0"
down_revision: str | None = "t4u5v6w7x8y9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audio_devices") as batch_op:
        batch_op.drop_column("input_count")
        batch_op.drop_column("output_count")
        batch_op.drop_column("input_connector")
        batch_op.drop_column("output_connector")
        batch_op.add_column(sa.Column("ports", sa.JSON(), nullable=True))

    with op.batch_alter_table("channel_patch_points") as batch_op:
        batch_op.drop_column("direction")

    # Existing rows have no port data yet; default them to an empty list so the
    # API can serialize them without a null check.
    op.execute("UPDATE audio_devices SET ports = '[]' WHERE ports IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("channel_patch_points") as batch_op:
        batch_op.add_column(sa.Column("direction", sa.String(length=8), nullable=True))

    with op.batch_alter_table("audio_devices") as batch_op:
        batch_op.drop_column("ports")
        batch_op.add_column(
            sa.Column(
                "input_connector",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("''"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "output_connector",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("''"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "output_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "input_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
