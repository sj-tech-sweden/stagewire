"""add unified graph devices and connection edges

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-10-29 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6g7h8"
down_revision: str | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "graph_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("attributes", JSON_TYPE, nullable=False),
        sa.Column("ports", JSON_TYPE, nullable=False),
        sa.Column("canvas_x_cm", sa.Float(), nullable=True),
        sa.Column("canvas_y_cm", sa.Float(), nullable=True),
        sa.Column("canvas_rotation", sa.Float(), nullable=False),
        sa.Column("case_parent_id", sa.Uuid(), nullable=True),
        sa.Column("stockwire_product_id", sa.String(length=64), nullable=True),
        sa.Column("stockwire_product_name", sa.String(length=255), nullable=True),
        sa.Column("stockwire_device_id", sa.String(length=64), nullable=True),
        sa.Column("stockwire_booked", sa.Boolean(), nullable=True),
        sa.Column("stockwire_request_status", sa.String(length=32), nullable=True),
        sa.Column("legacy_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["production_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_parent_id"], ["graph_devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("job_id", "domain", "case_parent_id", "stockwire_product_id", "legacy_ref"):
        op.create_index(f"ix_graph_devices_{column}", "graph_devices", [column])
    op.create_table(
        "graph_connection_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("signal", sa.String(length=16), nullable=False),
        sa.Column("src_device_id", sa.Uuid(), nullable=False),
        sa.Column("src_port", sa.String(length=64), nullable=False),
        sa.Column("dst_device_id", sa.Uuid(), nullable=False),
        sa.Column("dst_port", sa.String(length=64), nullable=False),
        sa.Column("channels", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=2), nullable=True),
        sa.Column("cable_label", sa.String(length=128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("attributes", JSON_TYPE, nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["production_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["src_device_id"], ["graph_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_device_id"], ["graph_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("job_id", "signal", "src_device_id", "dst_device_id"):
        op.create_index(f"ix_graph_connection_edges_{column}", "graph_connection_edges", [column])


def downgrade() -> None:
    op.drop_table("graph_connection_edges")
    op.drop_table("graph_devices")
