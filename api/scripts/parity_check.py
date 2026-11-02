"""Compare the graph-backed report contexts with their legacy twins for every job in a database.

Run it against a COPY of real data (set DATABASE_URL), before retiring the legacy tables:

    DATABASE_URL=postgresql+asyncpg://user:pw@host/copy python scripts/parity_check.py

For each job it syncs the graph from the legacy rows and compares the channel list and the patch
sheets as built from the legacy tables and as built from the graph. Prints the jobs that differ
and exits non-zero if there are any.
"""

import asyncio
import json
import sys

from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.reports import registry


def normal(value) -> str:
    def plain(item):
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        if hasattr(item, "__dict__"):
            return {k: v for k, v in vars(item).items() if not k.startswith("_")}
        return str(item)

    return json.dumps(value, default=plain, sort_keys=True)


async def main() -> int:
    checked = mismatched = 0
    async with db_mod.SessionLocal() as db:
        ids = list(await db.scalars(select(ProductionJob.id)))
    for job_id in ids:
        async with db_mod.SessionLocal() as db:
            pairs = (
                ("channels", registry._channel_list_context_legacy, registry._channel_list_context),
                (
                    "patchpoint_sheets",
                    registry._patch_sheet_context_legacy,
                    registry._patch_sheet_context,
                ),
            )
            for key, legacy, graph in pairs:
                checked += 1
                try:
                    old = (await legacy(db, job_id))[key]
                    new = (await graph(db, job_id))[key]
                except Exception as exc:  # noqa: BLE001 - report it, keep checking the rest
                    mismatched += 1
                    print(f"{job_id} {key}: error {type(exc).__name__}: {exc}")
                    continue
                if normal(old) != normal(new):
                    mismatched += 1
                    print(f"{job_id} {key}: differs")
    print(f"{len(ids)} jobs, {checked} comparisons, {mismatched} differences")
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
