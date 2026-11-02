"""Bring every job's rows from the legacy video tables onto the graph, once.

Video lives on the graph (``app/domains/graph/video_native.py``). A job whose video is still in
``video_input_lists``/``video_inputs``/``video_outputs`` is imported the next time its graph is
synced (``video_native.import_legacy``); this runs that for every job so nothing is left behind
before the tables are dropped. Safe to run again: imported rows are native and left alone.

    DATABASE_URL=postgresql+asyncpg://user:pw@host/db python scripts/import_legacy_video.py

Then ``scripts/parity_check.py`` must report no ``video_lists`` differences.
"""

import asyncio

from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.backfill import backfill_job


async def main() -> None:
    async with db_mod.SessionLocal() as db:
        ids = list(await db.scalars(select(ProductionJob.id)))
    for job_id in ids:
        async with db_mod.SessionLocal() as db:
            await backfill_job(db, job_id)
    print(f"synced {len(ids)} jobs")


if __name__ == "__main__":
    asyncio.run(main())
