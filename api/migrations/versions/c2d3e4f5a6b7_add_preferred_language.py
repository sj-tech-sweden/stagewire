"""add preferred_language to users

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "preferred_language",
            sa.String(16),
            server_default=sa.text("'en'"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "preferred_language")
