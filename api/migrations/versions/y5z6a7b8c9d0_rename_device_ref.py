"""rename the device ref from ``audio_devices:<id>`` to ``device:<id>``

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9

The table is gone; the ref on a device node is its identity (``graph/devices_native.py``), so it no
longer names a table. The power edge of a plugged device carries ``device.power:<id>`` instead of
``audio_devices.power:<id>``. Reversible: the downgrade puts the old prefixes back.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "y5z6a7b8c9d0"
down_revision: str | None = "x4y5z6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename(old: str, new: str) -> None:
    op.execute(
        f"UPDATE graph_devices SET legacy_ref = '{new}:' || substr(legacy_ref, {len(old) + 2}) "
        f"WHERE legacy_ref LIKE '{old}:%'"
    )
    op.execute(
        "UPDATE graph_connection_edges SET attributes = jsonb_set(attributes, '{legacy_ref}', "
        f"to_jsonb('{new}.power:' || substr(attributes->>'legacy_ref', {len(old) + 8}))) "
        f"WHERE attributes->>'legacy_ref' LIKE '{old}.power:%'"
    )


def upgrade() -> None:
    _rename("audio_devices", "device")


def downgrade() -> None:
    _rename("device", "audio_devices")
