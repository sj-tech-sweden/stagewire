"""store imported Wireless Workbench .shw show files

Revision ID: z8a9b0c1d2e3
Revises: z7a8b9c0d1e2

A channel list keeps the last ``.shw`` it imported so it can be re-exported with
Stagewire's coordinated frequencies written back into the same file.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z8a9b0c1d2e3"
down_revision: str | None = "z7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wwb_show_files",
        sa.Column(
            "list_node_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("graph_devices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_wwb_show_files_job_id", "wwb_show_files", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_wwb_show_files_job_id", table_name="wwb_show_files")
    op.drop_table("wwb_show_files")
