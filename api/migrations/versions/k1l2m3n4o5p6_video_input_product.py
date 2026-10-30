"""stockwire product on video inputs

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: str | None = "j0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("video_inputs") as batch:
        batch.add_column(sa.Column("stockwire_product_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("stockwire_product_name", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("video_inputs") as batch:
        batch.drop_column("stockwire_product_name")
        batch.drop_column("stockwire_product_id")
