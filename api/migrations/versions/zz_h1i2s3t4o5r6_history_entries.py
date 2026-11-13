"""add history entries (undo / redo / restore)

Revision ID: h1i2s3t4o5r6
Revises: n1b2c3d4e5f6
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h1i2s3t4o5r6"
down_revision = "n1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "history_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope_kind", sa.String(8), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("summary", sa.String(255), nullable=False, server_default=""),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column(
            "changes",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("undone", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("scope_kind", "scope_id", "seq", name="uq_history_scope_seq"),
    )
    op.create_index("ix_history_entries_scope_kind", "history_entries", ["scope_kind"])
    op.create_index("ix_history_entries_scope_id", "history_entries", ["scope_id"])


def downgrade() -> None:
    op.drop_index("ix_history_entries_scope_id", table_name="history_entries")
    op.drop_index("ix_history_entries_scope_kind", table_name="history_entries")
    op.drop_table("history_entries")
