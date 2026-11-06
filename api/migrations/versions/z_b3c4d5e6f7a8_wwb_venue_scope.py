"""wwb show files become venue-scoped (venues-as-template-jobs Phase 2)

Revision ID: z_b3c4d5e6f7a8
Revises: z_a1b2c3d4e5f6

A venue's Standard Base Rig keeps its own Wireless Workbench ``.shw`` show files, so the
storage row must be owned by a venue as well as a job. We add a nullable ``venue_id``
(foreign key to ``venues``) and relax ``job_id`` to nullable: exactly one of the two is
set, mirroring how the lighting fixture library is scoped.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z_b3c4d5e6f7a8"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wwb_show_files",
        sa.Column(
            "venue_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_wwb_show_files_venue_id", "wwb_show_files", ["venue_id"])
    # job_id was NOT NULL only because venues did not yet own show files; relax it so a
    # venue-owned row can carry venue_id instead.
    op.alter_column(
        "wwb_show_files",
        "job_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.drop_index("ix_wwb_show_files_venue_id", table_name="wwb_show_files")
    op.drop_column("wwb_show_files", "venue_id")
    op.alter_column(
        "wwb_show_files",
        "job_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
