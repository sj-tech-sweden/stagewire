"""history entries: store the number of changes next to the diffs

Revision ID: h2i3s4t5o6r7
Revises: h1i2s3t4o5r6
Create Date: 2026-11-13

The version list reads only counts, never the (large) diffs, so the count is kept in its own
column. It is a separate revision, and adds the column only when it is missing, because the first
history revision was already applied to development databases before the column existed.
"""

import sqlalchemy as sa
from alembic import op

revision = "h2i3s4t5o6r7"
down_revision = "h1i2s3t4o5r6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("history_entries")}
    if "change_count" in columns:
        return
    op.add_column(
        "history_entries",
        sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # existing entries: count the changes in their stored diffs
    length = "jsonb_array_length" if bind.dialect.name == "postgresql" else "json_array_length"
    op.execute(f"UPDATE history_entries SET change_count = {length}(changes)")


def downgrade() -> None:
    op.drop_column("history_entries", "change_count")
