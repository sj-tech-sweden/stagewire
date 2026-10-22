"""add notes to production_jobs

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "production_jobs",
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
    )


def downgrade():
    op.drop_column("production_jobs", "notes")
