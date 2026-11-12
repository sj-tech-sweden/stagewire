"""NetBox integration: per-job enable toggle

Revision ID: n1b2c3d4e5f6
Revises: f1xj0b1dnul1
Create Date: 2026-11-12

Adds a per-job ``netbox_enabled`` flag so individual production jobs can opt in
to (or out of) NetBox device mirroring and IP assignment on top of the global
integration setting. The NetBox custom fields / webhook / device-type
provisioning itself happens at runtime via ``POST /api/v1/netbox/provision`` and
is not a schema migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n1b2c3d4e5f6"
down_revision: str | None = "f1xj0b1dnul1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "production_jobs",
        sa.Column(
            "netbox_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("production_jobs", "netbox_enabled")
