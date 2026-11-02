"""plain ids for the columns that point at power nodes

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3

``audio_devices``, ``lighting_fixtures`` and ``stage_plot_elements`` each have a ``power_node_id``.
Power nodes are moving onto the graph, where a new node has no legacy row, so these columns now hold
the *public id* of the power node (the legacy id for a row that came from the table, a new uuid for
a new one) and are no longer foreign keys. A node with something plugged into it cannot be deleted
(the power rules refuse it), so nothing needs clearing. Nothing is dropped; the downgrade puts the
constraints back (it fails if a column holds an id with no legacy row).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s9t0u1v2w3x4"
down_revision: str | None = "r8s9t0u1v2w3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINTS = (
    ("audio_devices", "fk_audio_devices_power_node_id"),
    ("lighting_fixtures", "fk_lighting_fixtures_power_node_id"),
    ("stage_plot_elements", "fk_stage_plot_elements_power_node_id"),
)


def upgrade() -> None:
    for table, name in CONSTRAINTS:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="foreignkey")


def downgrade() -> None:
    for table, name in CONSTRAINTS:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                name, "power_nodes", ["power_node_id"], ["id"], ondelete="SET NULL"
            )
