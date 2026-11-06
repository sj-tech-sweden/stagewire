"""make fixture_types.job_id nullable

Revision ID: f1xj0b1dnul1
Revises: b2bfd20e8813
Create Date: 2026-11-06

The ``FixtureType`` ORM model declares ``job_id`` as nullable (a fixture type may
belong to a venue instead of a job), but the original create migration made the
column ``NOT NULL``. That drift broke venue-scoped fixture libraries, which insert
a row with ``venue_id`` set and ``job_id`` left NULL (see venue-base-rig.spec.ts:
"venue fixture library … stays venue-scoped"). Relax the constraint so the database
matches the model.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1xj0b1dnul1"
down_revision: str | None = "b2bfd20e8813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "fixture_types",
        "job_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "fixture_types",
        "job_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
