import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

API_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = API_ROOT / "migrations"

# Set this to a disposable Postgres DSN to exercise the full migration chain.
# It should use an async driver (e.g. postgresql+asyncpg://...) because the
# project's env.py builds an async engine; the test derives a sync URL for the
# post-run assertions. Leave unset to skip the Postgres run locally.
MIGRATION_TEST_DATABASE_URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")


def _alembic_config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def _async_url(raw: str) -> str:
    if "+asyncpg" in raw:
        return raw
    return raw.replace("postgresql://", "postgresql+asyncpg://")


def _sync_url(raw: str) -> str:
    return raw.replace("+asyncpg", "")


def test_migration_graph_has_a_single_head() -> None:
    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert heads == [script.get_current_head()], (
        f"Migration history must resolve to exactly one head, found: {heads}"
    )


def _all_revision_ids() -> set[str]:
    """Enumerate every revision id declared in the versions directory."""
    ids: set[str] = set()
    pattern = re.compile(r'^revision(?::\s*str)?\s*=\s*["\'](?P<rev>[^"\']+)["\']', re.MULTILINE)
    for path in sorted((MIGRATIONS_DIR / "versions").glob("*.py")):
        if path.name == "__init__.py":
            continue
        match = pattern.search(path.read_text())
        if match:
            ids.add(match.group("rev"))
    return ids


def test_migration_graph_is_fully_connected() -> None:
    """Every revision is reachable from base to head (no forks/orphans)."""
    script = ScriptDirectory.from_config(_alembic_config())
    base = script.get_base()
    head = script.get_current_head()
    assert base is not None, "Migration history has no base revision"

    all_ids = _all_revision_ids()
    assert all_ids, "No migration revisions found."

    all_revisions = script.get_revisions(list(all_ids))
    # walk_revisions yields head -> base; reverse for a base -> head order.
    walked = list(reversed(list(script.walk_revisions(base, head))))

    walked_ids = {rev.revision for rev in walked}
    assert walked_ids == all_ids, (
        "Migration graph is disconnected: "
        f"{all_ids - walked_ids} revision(s) are unreachable from base to "
        "head (a fork or orphaned branch)."
    )

    known = {rev.revision for rev in all_revisions}
    for rev in all_revisions:
        down = rev.down_revision
        for ref in down if isinstance(down, (list, tuple)) else [down]:
            assert ref in known or ref is None, (
                f"Revision {rev.revision} references missing down_revision {ref}."
            )

    # Ordering guard for the venue-branch fork regression: the trunk migration
    # that creates video_input_lists (c9d0e1f2a3b4) must run before the venue
    # base-rig migration (z2a3b4c5d6e7) that adds venue_id to it. Re-parenting
    # the venue branch onto the trunk tip (a9f8e7d6c5b4) guarantees this; forking
    # it off an earlier branchpoint lets alembic schedule z2 first and crash with
    # "relation video_input_lists does not exist".
    order = {rev.revision: i for i, rev in enumerate(walked)}
    created = "c9d0e1f2a3b4"
    altered = "z2a3b4c5d6e7"
    assert created in order, f"{created} (video_input_lists creation) missing from chain."
    assert altered in order, f"{altered} (venue base-rig ownership) missing from chain."
    assert order[created] < order[altered], (
        f"{created} must run before {altered} so video_input_lists exists when "
        "venue_id is added to it (venue-branch fork regression)."
    )


@pytest.mark.skipif(
    not MIGRATION_TEST_DATABASE_URL,
    reason="Set MIGRATION_TEST_DATABASE_URL (a disposable Postgres DSN) to run "
    "the full migration chain against a real database.",
)
def test_alembic_upgrade_head_succeeds_on_postgres() -> None:
    """Run the real `alembic upgrade head` against Postgres.

    This catches fork/ordering regressions that the SQLite create_all suite
    cannot (some migrations use PG-specific types and raw SQL, and the
    ordering of the venue branch relative to trunk table creation only matters
    on the real chain).
    """
    raw_url = MIGRATION_TEST_DATABASE_URL
    config = _alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()

    env = {**os.environ, "DATABASE_URL": _async_url(raw_url)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(API_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, "alembic upgrade head failed:\n" + result.stderr

    sync_url = _sync_url(raw_url)
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        recorded = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert recorded == head, f"alembic_version is {recorded!r}, expected head {head!r}."

        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        assert "video_input_lists" in tables, "video_input_lists table missing after upgrade."

        video_input_lists_columns = {
            col["name"] for col in inspector.get_columns("video_input_lists")
        }
        assert "venue_id" in video_input_lists_columns, (
            "video_input_lists.venue_id missing: the venue base-rig migration "
            "ran before the trunk created video_input_lists (fork regression)."
        )

        # The venue geometry migration (z1a2b3c4d5e6) adds footprint_shape to
        # venues; its presence proves the whole venue branch ran after the trunk.
        venues_columns = {col["name"] for col in inspector.get_columns("venues")}
        assert "footprint_shape" in venues_columns, (
            "venues.footprint_shape missing: the venue geometry migration did "
            "not run (venue branch dropped from the chain)."
        )
    engine.dispose()
