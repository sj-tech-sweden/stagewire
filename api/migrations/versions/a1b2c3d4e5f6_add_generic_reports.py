"""add generic report templates and letterheads

Revision ID: a1b2c3d4e5f6
Revises: z0a1b2c3d4e5
Create Date: 2026-10-26 08:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "z0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type():
    return sa.Uuid(as_uuid=True).with_variant(postgresql.UUID(as_uuid=True), "postgresql")


def upgrade() -> None:
    op.create_table(
        "report_letterheads",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("page_width_pt", sa.Float(), nullable=False),
        sa.Column("page_height_pt", sa.Float(), nullable=False),
        sa.Column("margin_top_mm", sa.Float(), nullable=False, server_default="20"),
        sa.Column("margin_bottom_mm", sa.Float(), nullable=False, server_default="20"),
        sa.Column("margin_left_mm", sa.Float(), nullable=False, server_default="20"),
        sa.Column("margin_right_mm", sa.Float(), nullable=False, server_default="20"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("file_name"),
    )
    op.create_index(
        "ix_report_letterheads_is_default", "report_letterheads", ["is_default"], unique=False
    )
    op.create_table(
        "report_templates",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("letterhead_id", _uuid_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["letterhead_id"], ["report_letterheads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_templates_domain", "report_templates", ["domain"], unique=False)
    op.create_index(
        "ix_report_templates_report_type", "report_templates", ["report_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_report_templates_report_type", table_name="report_templates")
    op.drop_index("ix_report_templates_domain", table_name="report_templates")
    op.drop_table("report_templates")
    op.drop_index("ix_report_letterheads_is_default", table_name="report_letterheads")
    op.drop_table("report_letterheads")
