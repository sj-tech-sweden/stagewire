"""fixture types with several DMX modes; fixtures reference a type and a mode

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-30 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fixture_types",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(255), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("stockwire_product_id", sa.String(64), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("power_watts", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_fixture_types_job_id", "fixture_types", ["job_id"])
    op.create_table(
        "fixture_modes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "fixture_type_id",
            sa.Uuid(),
            sa.ForeignKey("fixture_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("footprint", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_fixture_modes_fixture_type_id", "fixture_modes", ["fixture_type_id"])
    op.add_column("lighting_fixtures", sa.Column("fixture_type_id", sa.Uuid(), nullable=True))
    op.add_column("lighting_fixtures", sa.Column("fixture_mode_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_lighting_fixtures_fixture_type_id",
        "lighting_fixtures",
        "fixture_types",
        ["fixture_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_lighting_fixtures_fixture_mode_id",
        "lighting_fixtures",
        "fixture_modes",
        ["fixture_mode_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_lighting_fixtures_fixture_type_id", "lighting_fixtures", ["fixture_type_id"])
    op.create_index("ix_lighting_fixtures_fixture_mode_id", "lighting_fixtures", ["fixture_mode_id"])


def downgrade() -> None:
    op.drop_index("ix_lighting_fixtures_fixture_mode_id", table_name="lighting_fixtures")
    op.drop_index("ix_lighting_fixtures_fixture_type_id", table_name="lighting_fixtures")
    op.drop_constraint("fk_lighting_fixtures_fixture_mode_id", "lighting_fixtures", type_="foreignkey")
    op.drop_constraint("fk_lighting_fixtures_fixture_type_id", "lighting_fixtures", type_="foreignkey")
    op.drop_column("lighting_fixtures", "fixture_mode_id")
    op.drop_column("lighting_fixtures", "fixture_type_id")
    op.drop_index("ix_fixture_modes_fixture_type_id", table_name="fixture_modes")
    op.drop_table("fixture_modes")
    op.drop_index("ix_fixture_types_job_id", table_name="fixture_types")
    op.drop_table("fixture_types")
