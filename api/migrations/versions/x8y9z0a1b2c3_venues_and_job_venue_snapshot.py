"""venues library and job venue snapshot

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-10-25 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x8y9z0a1b2c3"
down_revision: str | None = "w7x8y9z0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("venue_width_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("venue_height_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("stage_x_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("stage_y_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("stage_width_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("stage_height_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column(
            "background_image_url",
            sa.String(length=1024),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("propagated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("production_jobs", sa.Column("venue_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_production_jobs_venue_id",
        "production_jobs",
        "venues",
        ["venue_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_production_jobs_venue_id", "production_jobs", ["venue_id"])
    op.add_column(
        "production_jobs",
        sa.Column("venue_width_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "production_jobs",
        sa.Column("venue_height_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "production_jobs",
        sa.Column("stage_x_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "production_jobs",
        sa.Column("stage_y_cm", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "production_jobs",
        sa.Column(
            "venue_background_image_url",
            sa.String(length=1024),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )


def downgrade() -> None:
    op.drop_column("production_jobs", "venue_background_image_url")
    op.drop_column("production_jobs", "stage_y_cm")
    op.drop_column("production_jobs", "stage_x_cm")
    op.drop_column("production_jobs", "venue_height_cm")
    op.drop_column("production_jobs", "venue_width_cm")
    op.drop_index("ix_production_jobs_venue_id", table_name="production_jobs")
    op.drop_constraint("fk_production_jobs_venue_id", "production_jobs", type_="foreignkey")
    op.drop_column("production_jobs", "venue_id")
    op.drop_table("venues")
