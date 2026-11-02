"""power connector fields on connector kinds

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: str | None = "h8i9j0k1l2m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("connector_kinds") as batch:
        batch.add_column(sa.Column("power", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("amps", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("phases", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("circuits", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("connector_kinds") as batch:
        batch.drop_column("circuits")
        batch.drop_column("phases")
        batch.drop_column("amps")
        batch.drop_column("power")
