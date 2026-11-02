"""plain ids for the columns that point at rigging points

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1

``audio_devices``, ``lighting_fixtures`` and ``stage_plot_elements`` each have a
``rigging_point_id``. Rigging points are moving onto the graph, where a new point has no legacy row,
so these columns now hold the *public id* of the point node (the legacy id for a row that came from
the table, the node's own id for a new one) and are no longer foreign keys. Deleting a point clears
them in code instead of ``ON DELETE SET NULL``. Nothing is dropped; the downgrade puts the
constraints back (it fails if a column holds an id with no legacy row).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "q7r8s9t0u1v2"
down_revision: str | None = "p6q7r8s9t0u1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINTS = (
    ("audio_devices", "fk_audio_devices_rigging_point_id"),
    ("lighting_fixtures", "fk_lighting_fixtures_rigging_point_id"),
    ("stage_plot_elements", "fk_stage_plot_elements_rigging_point_id"),
)


def upgrade() -> None:
    for table, name in CONSTRAINTS:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="foreignkey")


def downgrade() -> None:
    for table, name in CONSTRAINTS:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                name, "rigging_points", ["rigging_point_id"], ["id"], ondelete="SET NULL"
            )
