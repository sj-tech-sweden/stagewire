"""source and input ports on video chain steps

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-29 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("video_patch_points", "video_output_patch_points"):
        op.add_column(
            table,
            sa.Column("source_port", sa.String(length=32), nullable=False, server_default=""),
        )
        op.add_column(
            table,
            sa.Column("input_port", sa.String(length=32), nullable=False, server_default=""),
        )


def downgrade() -> None:
    for table in ("video_output_patch_points", "video_patch_points"):
        op.drop_column(table, "input_port")
        op.drop_column(table, "source_port")
