"""add venue cable_plan

A venue's Standard Base Rig can hold cable raceways (cableways) and routing settings, stored the
same way a job's cable_plan is (a `cableways` array plus routing `settings`). Jobs clone these as
a starting point and add their own runs, so the venue owns the fixed infrastructure (trays,
conduits). Model change only — no other tables are touched here.

Revision ID: b2bfd20e8813
Revises: z_b3c4d5e6f7a8
Create Date: 2026-11-06 09:30:31.475102

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2bfd20e8813"
down_revision: str | None = "z_b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'venues',
        sa.Column(
            'cable_plan',
            postgresql.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column('venues', 'cable_plan')
