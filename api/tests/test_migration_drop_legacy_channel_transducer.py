import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.domains.venues.models  # noqa: F401

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "b8c9d0e1f2a3_drop_legacy_channel_transducer.py"
)
MIGRATION_SPEC = importlib.util.spec_from_file_location(
    "drop_legacy_channel_transducer", MIGRATION_PATH
)
assert MIGRATION_SPEC is not None
assert MIGRATION_SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(MIGRATION_SPEC)
MIGRATION_SPEC.loader.exec_module(MIGRATION)


def _run_upgrade(connection: sa.Connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        MIGRATION.upgrade()


def test_upgrade_removes_legacy_transducer_and_preserves_device_value() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE audio_channel_patches "
                "(id INTEGER PRIMARY KEY, device VARCHAR(255), transducer VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO audio_channel_patches (device, transducer) "
                "VALUES ('', 'Legacy microphone')"
            )
        )

        _run_upgrade(connection)

        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("audio_channel_patches")
        }
        row = connection.execute(sa.text("SELECT device FROM audio_channel_patches")).one()

    assert "transducer" not in columns
    assert row.device == "Legacy microphone"
    engine.dispose()


def test_upgrade_is_safe_when_legacy_transducer_is_already_absent() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE audio_channel_patches (id INTEGER PRIMARY KEY, device VARCHAR(255))"
            )
        )

        _run_upgrade(connection)

        columns = {
            column["name"] for column in sa.inspect(connection).get_columns("audio_channel_patches")
        }

    assert "device" in columns
    assert "transducer" not in columns
    engine.dispose()
