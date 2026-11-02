"""plain ids for the two columns that point at video rows

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7

``stage_plot_elements.linked_video_input_id`` and ``audio_devices.video_list_id`` pointed at the
legacy video tables. Video is moving onto the graph, where a new input or list has no legacy row,
so these columns now hold the *public id* of the video node (the legacy id for rows that came from
the tables, the node's own id for new ones) and can no longer be foreign keys. Deleting a video
input or list clears them in code (``video.service.delete``) instead of ``ON DELETE SET NULL``.
Nothing is dropped; the downgrade puts the constraints back (it fails if a column holds an id that
has no legacy row, which is the point at which a downgrade is no longer possible).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: str | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stage_plot_elements") as batch:
        batch.drop_constraint("fk_stage_plot_elements_linked_video_input_id", type_="foreignkey")
    with op.batch_alter_table("audio_devices") as batch:
        batch.drop_constraint("fk_audio_devices_video_list_id", type_="foreignkey")


def downgrade() -> None:
    with op.batch_alter_table("audio_devices") as batch:
        batch.create_foreign_key(
            "fk_audio_devices_video_list_id",
            "video_input_lists",
            ["video_list_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("stage_plot_elements") as batch:
        batch.create_foreign_key(
            "fk_stage_plot_elements_linked_video_input_id",
            "video_inputs",
            ["linked_video_input_id"],
            ["id"],
            ondelete="SET NULL",
        )
