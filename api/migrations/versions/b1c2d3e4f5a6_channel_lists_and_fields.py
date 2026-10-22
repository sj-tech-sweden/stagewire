"""channel lists + richer channel rows

Revision ID: b1c2d3e4f5a6
Revises: aa46e8245308
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "aa46e8245308"
branch_labels = None
depends_on = None


def upgrade():
    # 1. New channel-list table (named, user-created lists per job)
    op.create_table(
        "audio_channel_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("production_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audio_channel_lists_job_id", "audio_channel_lists", ["job_id"])

    # 2. Reparent existing channel patches onto a default list per job (backfill)
    op.execute(
        """
        INSERT INTO audio_channel_lists (id, job_id, name, position, created_at)
        SELECT gen_random_uuid(), job_id, 'Input List', 0, now()
        FROM (SELECT DISTINCT job_id FROM audio_channel_patches) AS d
        """
    )

    # 3. Add the new parent column (nullable first)
    op.add_column(
        "audio_channel_patches",
        sa.Column("channel_list_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE audio_channel_patches AS p
        SET channel_list_id = (
            SELECT id FROM audio_channel_lists AS l WHERE l.job_id = p.job_id LIMIT 1
        )
        """
    )
    op.alter_column(
        "audio_channel_patches",
        "channel_list_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_audio_channel_patches_channel_list_id",
        "audio_channel_patches",
        "audio_channel_lists",
        ["channel_list_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 4. Richer channel fields (SoundDocs-style)
    op.add_column("audio_channel_patches", sa.Column("input_type", sa.String(64), nullable=True))
    op.add_column("audio_channel_patches", sa.Column("device", sa.String(255), nullable=True))
    op.add_column(
        "audio_channel_patches",
        sa.Column("stereo", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("audio_channel_patches", sa.Column("stereo_channel", sa.Integer(), nullable=True))
    op.add_column("audio_channel_patches", sa.Column("connection_type", sa.String(64), nullable=True))
    op.add_column("audio_channel_patches", sa.Column("connection_details", sa.JSON(), nullable=True))

    op.alter_column(
        "audio_channel_patches", "stereo", server_default=None
    )

    # 5. Drop the old denormalised job_id column on patches
    op.drop_constraint(
        "audio_channel_patches_job_id_fkey", "audio_channel_patches", type_="foreignkey"
    )
    op.drop_column("audio_channel_patches", "job_id")


def downgrade():
    op.add_column(
        "audio_channel_patches",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE audio_channel_patches AS p
        SET job_id = (SELECT job_id FROM audio_channel_lists AS l WHERE l.id = p.channel_list_id)
        """
    )
    op.alter_column(
        "audio_channel_patches", "job_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False
    )
    op.create_foreign_key(
        "audio_channel_patches_job_id_fkey",
        "audio_channel_patches",
        "production_jobs",
        ["job_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_column("audio_channel_patches", "connection_details")
    op.drop_column("audio_channel_patches", "connection_type")
    op.drop_column("audio_channel_patches", "stereo_channel")
    op.drop_column("audio_channel_patches", "stereo")
    op.drop_column("audio_channel_patches", "device")
    op.drop_column("audio_channel_patches", "input_type")

    op.drop_constraint(
        "fk_audio_channel_patches_channel_list_id", "audio_channel_patches", type_="foreignkey"
    )
    op.drop_column("audio_channel_patches", "channel_list_id")
    op.drop_index("ix_audio_channel_lists_job_id", table_name="audio_channel_lists")
    op.drop_table("audio_channel_lists")
