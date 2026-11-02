"""structured wireless frequency fields

Revision ID: a1b2c3d4e5f6
Revises: z6a7b8c9d0e1

Frequencies were stored as free text (``wireless_frequency``). They now live on the
channel node as structured fields (``wireless_frequency_mhz``, ``wireless_group``,
``wireless_channel``). This converts the legacy string into the numeric MHz value and
drops the old key.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "z6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE graph_devices
        SET attributes = jsonb_set(
            attributes,
            '{wireless_frequency_mhz}',
            to_jsonb(
                (
                    regexp_replace(
                        replace(attributes->>'wireless_frequency', ',', '.'),
                        '[^0-9.]',
                        '',
                        'g'
                    )
                )::numeric
            ),
            true
        )
        WHERE attributes ? 'wireless_frequency'
          AND attributes->>'wireless_frequency' ~ '[0-9]'
        """
    )
    op.execute(
        "UPDATE graph_devices SET attributes = attributes - 'wireless_frequency' "
        "WHERE attributes ? 'wireless_frequency'"
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE graph_devices
        SET attributes = jsonb_set(
            attributes,
            '{wireless_frequency}',
            to_jsonb((attributes->>'wireless_frequency_mhz') || ' MHz'),
            true
        )
        WHERE attributes ? 'wireless_frequency_mhz'
        """
    )
    op.execute(
        "UPDATE graph_devices SET attributes = attributes - 'wireless_frequency_mhz' "
        "WHERE attributes ? 'wireless_frequency_mhz'"
    )
    op.execute(
        "UPDATE graph_devices SET attributes = attributes - 'wireless_group' "
        "WHERE attributes ? 'wireless_group'"
    )
    op.execute(
        "UPDATE graph_devices SET attributes = attributes - 'wireless_channel' "
        "WHERE attributes ? 'wireless_channel'"
    )
