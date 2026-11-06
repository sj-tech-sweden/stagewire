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

    # Ordering guard for the venue branch: the unified graph migration that creates
    # graph_devices (c3d4e5f6g7h8) must run before the venue base-rig merge
    # (z9b0c1d2e3f4) that adds venue_id to it and makes job_id nullable. The venue
    # geometry migration (z1a2b3c4d5e6) and the reports head (d4e5f6a7b8c9) must
    # also precede the merge. A fork that scheduled the venue migration before those
    # would crash with "relation graph_devices does not exist".
    order = {rev.revision: i for i, rev in enumerate(walked)}
    graph_root = "c3d4e5f6g7h8"
    geometry = "z1a2b3c4d5e6"
    reports_head = "d4e5f6a7b8c9"
    merge = "z9b0c1d2e3f4"
    assert graph_root in order, f"{graph_root} (unified graph) missing from chain."
    assert geometry in order, f"{geometry} (venue geometry) missing from chain."
    assert reports_head in order, f"{reports_head} (reports head) missing from chain."
    assert merge in order, f"{merge} (venue base-rig merge) missing from chain."
    assert order[graph_root] < order[merge], (
        f"{graph_root} must run before {merge} so graph_devices exists when the "
        "venue base-rig migration alters it."
    )
    assert order[geometry] < order[merge], f"{geometry} must run before {merge}."
    assert order[reports_head] < order[merge], f"{reports_head} must run before {merge}."


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
        assert "graph_devices" in tables, "graph_devices table missing after upgrade."

        graph_devices_columns = {col["name"] for col in inspector.get_columns("graph_devices")}
        # The venue base-rig migration (z9b0c1d2e3f4) adds venue_id to graph_devices
        # and makes job_id nullable so a venue-owned rig carries job_id NULL.
        assert "venue_id" in graph_devices_columns, (
            "graph_devices.venue_id missing: the venue base-rig migration did "
            "not run (venue branch dropped from the chain)."
        )
        job_id_col = next(
            c for c in inspector.get_columns("graph_devices") if c["name"] == "job_id"
        )
        assert job_id_col["nullable"], "graph_devices.job_id must be nullable for venue rigs."

        # The venue geometry migration (z1a2b3c4d5e6) adds footprint_shape to venues.
        venues_columns = {col["name"] for col in inspector.get_columns("venues")}
        assert "footprint_shape" in venues_columns, (
            "venues.footprint_shape missing: the venue geometry migration did "
            "not run (venue branch dropped from the chain)."
        )
    engine.dispose()
