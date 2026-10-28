"""power circuits can be single-phase (on one line) or three-phase

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-10-30 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "power_circuits",
        sa.Column("phases", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column(
        "power_circuits",
        "phase",
        existing_type=sa.String(4),
        nullable=True,
        existing_server_default="L1",
    )


def downgrade() -> None:
    op.execute("UPDATE power_circuits SET phase = 'L1' WHERE phase IS NULL")
    op.alter_column(
        "power_circuits",
        "phase",
        existing_type=sa.String(4),
        nullable=False,
        server_default="L1",
    )
    op.drop_column("power_circuits", "phases")
