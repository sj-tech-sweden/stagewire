"""merge venue feature branch into trunk

The venue geometry/base-rig feature (z1a2b3c4d5e6 -> z2a3b4c5d6e7) branched off
the z0a1b2c3d4e5 branchpoint and was never merged back, leaving the migration
history with two heads. This empty merge migration combines the trunk head
(a9f8e7d6c5b4) with the venue branch head so `alembic upgrade head` resolves
to a single head.

Revision ID: z3a4b5c6d7e8
Revises: a9f8e7d6c5b4, z2a3b4c5d6e7
Create Date: 2026-11-04 12:30:00
"""

from collections.abc import Sequence

revision: str = "z3a4b5c6d7e8"
down_revision: tuple[str, ...] = ("a9f8e7d6c5b4", "z2a3b4c5d6e7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No schema change: this only unifies the two heads into one.
    pass


def downgrade() -> None:
    pass
