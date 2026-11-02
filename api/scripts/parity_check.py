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
import uuid

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


async def _dmx_legacy(db, job_id):
    """The job's universes from the tables; a step is named by the device or fixture it is."""
    from app.domains.lighting.models import DmxStep, DmxUniverse, LightingFixture

    fixtures = {
        f.id: f
        for f in await db.scalars(select(LightingFixture).where(LightingFixture.job_id == job_id))
    }

    def who(step):
        if step.fixture_id:
            fixture = fixtures.get(step.fixture_id)
            if fixture is None:
                return None
            return (
                ("device", str(fixture.device_id))
                if fixture.device_id
                else (
                    "fixture",
                    str(fixture.id),
                )
            )
        return ("device", str(step.device_id))

    out = []
    for u in await db.scalars(
        select(DmxUniverse).where(DmxUniverse.job_id == job_id).order_by(DmxUniverse.number)
    ):
        rows = (
            await db.scalars(
                select(DmxStep).where(DmxStep.universe_id == u.id).order_by(DmxStep.position)
            )
        ).all()
        out.append(
            {
                "id": str(u.id),
                "number": u.number,
                "name": u.name or "",
                "notes": u.notes or "",
                "source": [
                    str(u.source_device_id) if u.source_device_id else None,
                    u.source_port or "",
                ],
                "steps": [
                    [
                        str(r.id),
                        r.position,
                        who(r),
                        str(r.parent_id) if r.parent_id else None,
                        r.in_port or "",
                        r.out_port or "",
                        r.connector or "",
                        r.notes or "",
                    ]
                    for r in rows
                    if who(r) is not None
                ],
            }
        )
    return out


async def _dmx_graph(db, job_id):
    from app.domains.graph.backfill import backfill_job
    from app.domains.graph.ids import public_id
    from app.domains.graph.models import GraphDevice

    await backfill_job(db, job_id)
    nodes = {
        n.id: n for n in await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))
    }

    def who(node):
        ref = node.legacy_ref or ""
        table, _, raw = ref.partition(":")
        return ("fixture" if table == "lighting_fixtures" else "device", raw)

    out = []
    for n in sorted(
        (n for n in nodes.values() if n.kind == "dmx_universe"),
        key=lambda n: n.attributes["number"],
    ):
        a = n.attributes
        source = nodes.get(uuid.UUID(a["source_device_id"])) if a.get("source_device_id") else None
        steps = [
            [
                s["step_id"],
                s["position"],
                who(nodes[uuid.UUID(s["node_id"])]) if uuid.UUID(s["node_id"]) in nodes else None,
                s["parent_id"],
                s["in_port"],
                s["out_port"],
                s["connector"],
                s["notes"],
            ]
            for s in sorted(a.get("steps", []), key=lambda s: s["position"])
        ]
        out.append(
            {
                "id": str(public_id(n)),
                "number": a["number"],
                "name": a.get("name", ""),
                "notes": n.notes or "",
                "source": [who(source)[1] if source else None, a.get("source_port", "")],
                "steps": steps,
            }
        )
    return out


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
            checked += 1
            try:
                if await _dmx_legacy(db, job_id) != await _dmx_graph(db, job_id):
                    mismatched += 1
                    print(f"{job_id} dmx_universes: differs")
            except Exception as exc:  # noqa: BLE001
                mismatched += 1
                print(f"{job_id} dmx_universes: error {type(exc).__name__}: {exc}")
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
