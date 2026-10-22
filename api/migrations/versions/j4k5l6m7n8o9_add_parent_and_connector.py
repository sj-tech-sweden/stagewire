"""add parent_id and bus_connector to output patch points

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j4k5l6m7n8o9"
down_revision: str | None = "i3j4k5l6m7n8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "output_patch_points",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_output_patch_points_parent_id",
        "output_patch_points",
        "output_patch_points",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "output_patch_points",
        sa.Column("bus_connector", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("output_patch_points", "bus_connector")
    op.drop_constraint(
        "fk_output_patch_points_parent_id", "output_patch_points", type_="foreignkey"
    )
    op.drop_column("output_patch_points", "parent_id")
