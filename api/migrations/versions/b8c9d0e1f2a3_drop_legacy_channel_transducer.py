"""drop legacy channel transducer column

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-03 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("audio_channel_patches")
    }
    if "transducer" not in columns:
        return

    op.execute(
        "UPDATE audio_channel_patches "
        "SET device = transducer "
        "WHERE (device IS NULL OR device = '') AND transducer IS NOT NULL AND transducer != ''"
    )
    op.drop_column("audio_channel_patches", "transducer")


def downgrade() -> None:
    pass
