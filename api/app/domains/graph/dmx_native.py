"""DMX universes and their chains authored directly on the graph (no legacy tables behind them).

Same shape as ``video_native``. A ``dmx_universe`` node keeps its chain as the canonical data in
``attributes.steps`` and its source in ``attributes.source_device_id`` / ``source_port``; the edges
the web app and the graph tools read are rebuilt from them by ``rebuild`` whenever they change.

A step is ``{step_id, position, node_id, parent_id, in_port, out_port, connector, notes}``:
``node_id`` is the *graph node* the signal passes through (a gear device, or a fixture; a device
that carries a fixture is one node, so it steps as the fixture), ``parent_id`` the step it takes
DMX from (None: straight from the universe). A step whose node is gone is skipped when the edges
are built and dropped by ``drop_node``.

Ids. A universe's public id (``ids.public_id``) is the legacy id for imported rows and its node id
for new ones; a step's id is the legacy step id for imported steps and a new uuid for new ones.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.backfill import FAN_OUT, Backfill
from app.domains.graph.models import ConnectionEdge, GraphDevice

STEP_KEYS = ("in_port", "out_port", "connector", "notes")


def universe_node(
    job_id: uuid.UUID, number: int, name: str = "", notes: str = "", source: dict | None = None
) -> GraphDevice:
    return GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id,
        domain="lighting",
        kind="dmx_universe",
        name=name or f"Universe {number}",
        notes=notes,
        position=number,
        attributes={
            "number": number,
            "name": name,
            "source_port": (source or {}).get("port", ""),
            "source_device_id": (source or {}).get("device_id"),
            "steps": [],
        },
        ports=[
            {"id": "in", "direction": "in", "signal": "dmx"},
            {"id": "out", "direction": "out", "signal": "dmx", "max_connections": FAN_OUT},
        ],
    )


def new_step(position: int, node_id: uuid.UUID, step=None, parent_id: str | None = None) -> dict:
    return {
        "step_id": str(uuid.uuid4()),
        "position": position,
        "node_id": str(node_id),
        "parent_id": parent_id,
        **{key: getattr(step, key, "") or "" for key in STEP_KEYS},
    }


async def rebuild(db: AsyncSession, node: GraphDevice, steps: list[dict] | None = None) -> None:
    """Store the steps (when given) and rebuild the universe's edges from its attributes."""
    attributes = dict(node.attributes or {})
    if steps is not None:
        attributes["steps"] = sorted(steps, key=lambda s: s.get("position") or 0)
    steps = attributes.get("steps", [])
    for edge in (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == node.job_id, ConnectionEdge.signal == "dmx"
            )
        )
    ).all():
        if (edge.attributes or {}).get("chain") == str(node.id):
            await db.delete(edge)
    await db.flush()

    wanted = {uuid.UUID(s["node_id"]) for s in steps}
    if attributes.get("source_device_id"):
        wanted.add(uuid.UUID(attributes["source_device_id"]))
    nodes = {
        d.id: d
        for d in (
            await db.scalars(select(GraphDevice).where(GraphDevice.id.in_(wanted or {node.id})))
        ).all()
        if d.job_id == node.job_id
    }
    number = attributes.get("number")
    new_edges: list[ConnectionEdge] = []

    def edge(src, sport, dst, dport, attrs) -> None:
        new_edges.append(
            ConnectionEdge(
                id=uuid.uuid4(),
                job_id=node.job_id,
                signal="dmx",
                src_device_id=src.id,
                src_port=sport,
                dst_device_id=dst.id,
                dst_port=dport,
                channels=1,
                attributes={"chain": str(node.id), "universe": number, **attrs},
            )
        )

    source = (
        nodes.get(uuid.UUID(attributes["source_device_id"]))
        if attributes.get("source_device_id")
        else None
    )
    if source is not None:
        port = attributes.get("source_port") or ""
        edge(
            source,
            Backfill.named_port(source, "out", "dmx", port),
            node,
            "in",
            {"source_port": port},
        )
    by_id = {s["step_id"]: s for s in steps}
    for step in steps:
        target = nodes.get(uuid.UUID(step["node_id"]))
        parent_step = by_id.get(step["parent_id"]) if step["parent_id"] else None
        parent = nodes.get(uuid.UUID(parent_step["node_id"])) if parent_step else node
        if target is None or parent is None:
            continue
        edge(
            parent,
            Backfill.named_port(parent, "out", "dmx", parent_step["out_port"], step["connector"])
            if parent_step
            else "out",
            target,
            Backfill.named_port(target, "in", "dmx", step["in_port"], step["connector"]),
            {
                "step_id": step["step_id"],
                "position": step["position"],
                "parent_id": step["parent_id"],
                **{key: step[key] or "" for key in STEP_KEYS},
            },
        )
    node.attributes = attributes
    db.add_all(new_edges)
    await db.flush()


def translate_patch(node: GraphDevice, data: dict) -> dict:
    """A universe's name and number are kept in its attributes and on the node (the old mirror)."""
    if node.kind != "dmx_universe":
        return data
    attrs = dict(data.get("attributes") or {})
    if data.get("name") is not None:
        attrs["name"] = data["name"]
    if data.get("position") is not None and "number" not in attrs:
        attrs["number"] = max(1, data["position"])
    if attrs.get("number") is not None and data.get("position") is None:
        data = {**data, "position": attrs["number"]}
    return {**data, "attributes": attrs} if attrs else data


async def after_patch(db: AsyncSession, node: GraphDevice, data: dict) -> None:
    """The universe number and source port are on its edges too: rebuild them."""
    sent = data.get("attributes") or {}
    if node.kind != "dmx_universe":
        return
    if "number" in sent:
        others = await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == node.job_id,
                GraphDevice.kind == "dmx_universe",
                GraphDevice.id != node.id,
            )
        )
        if any((o.attributes or {}).get("number") == sent["number"] for o in others.all()):
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Universe {sent['number']} already exists"
            )
    if "source_port" in sent or "number" in sent:
        await rebuild(db, node)


async def step_from_edge(db: AsyncSession, edge: ConnectionEdge, data: dict) -> bool:
    """An edge PATCH of ports/connector/notes is a change to the step (or the source) it stands for.

    The edge already carries the values; only the canonical data is updated, no rebuild.
    """
    attrs = edge.attributes or {}
    chain, step_id = attrs.get("chain"), attrs.get("step_id")
    sent = data.get("attributes") or {}
    if edge.signal != "dmx" or not chain:
        return False
    node = await db.get(GraphDevice, uuid.UUID(chain))
    if node is None or node.kind != "dmx_universe":
        return False
    attributes = dict(node.attributes or {})
    if step_id:
        changed = {k: sent[k] or "" for k in STEP_KEYS if k in sent}
        if not changed:
            return False
        attributes["steps"] = [
            {**s, **changed} if s["step_id"] == step_id else s for s in attributes.get("steps", [])
        ]
    elif "source_port" in sent:
        attributes["source_port"] = sent["source_port"] or ""
    else:
        return False
    node.attributes = attributes
    await db.flush()
    return True


async def delete_step_edge(db: AsyncSession, edge: ConnectionEdge) -> bool:
    """Deleting a connection removes its step; the steps below it move up to its parent."""
    attrs = edge.attributes or {}
    chain, step_id = attrs.get("chain"), attrs.get("step_id")
    if edge.signal != "dmx" or not chain:
        return False
    node = await db.get(GraphDevice, uuid.UUID(chain))
    if node is None or node.kind != "dmx_universe":
        return False
    if not step_id:  # the source edge: the universe has no source any more
        await rebuild_without_source(db, node)
        return True
    steps = (node.attributes or {}).get("steps", [])
    gone = next((s for s in steps if s["step_id"] == step_id), None)
    if gone is None:
        return False
    await rebuild(
        db,
        node,
        [
            {**s, "parent_id": gone["parent_id"]} if s["parent_id"] == step_id else s
            for s in steps
            if s["step_id"] != step_id
        ],
    )
    return True


async def rebuild_without_source(db: AsyncSession, node: GraphDevice) -> None:
    node.attributes = {**(node.attributes or {}), "source_device_id": None, "source_port": ""}
    await rebuild(db, node)


async def drop_node(db: AsyncSession, job_id: uuid.UUID, node_id: uuid.UUID) -> None:
    """A device or fixture node is going away: it leaves every universe's chain (and source)."""
    for universe in (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == job_id, GraphDevice.kind == "dmx_universe"
            )
        )
    ).all():
        attributes = dict(universe.attributes or {})
        steps = attributes.get("steps", [])
        gone = {s["step_id"]: s for s in steps if s["node_id"] == str(node_id)}
        lost_source = attributes.get("source_device_id") == str(node_id)
        if not gone and not lost_source:
            continue
        kept = []
        for step in steps:
            if step["step_id"] in gone:
                continue
            parent = step["parent_id"]
            while parent in gone:  # the nearest ancestor that stays
                parent = gone[parent]["parent_id"]
            kept.append({**step, "parent_id": parent})
        if lost_source:
            attributes.update(source_device_id=None, source_port="")
            universe.attributes = attributes
        await rebuild(db, universe, kept)


async def require_step_nodes(db: AsyncSession, job_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    for node_id in ids:
        node = await db.get(GraphDevice, node_id)
        if node is None or node.job_id != job_id or node.kind in ("dmx_universe", "channel_list"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job"
            )


# ---- one-off import of the legacy DMX tables ---------------------------------------------------


async def import_legacy(db: AsyncSession, job_id: uuid.UUID) -> bool:
    """Bring a job's rows from ``dmx_universes``/``dmx_steps`` onto the graph. True if changed.

    A universe may be a mirror node (``legacy_ref``), not on the graph yet, or already native
    (``attributes.legacy_id``). This makes each legacy universe native: the legacy id becomes
    ``attributes.legacy_id`` (its public id), the steps come from the step table (a fixture step
    becomes the node of the fixture, i.e. its device's node when it has one) and the edges are
    rebuilt. A native universe is left alone, so graph edits are never overwritten. Needs the
    device and fixture nodes, so it runs after the sync. It reads the tables only to import; it goes
    with them when they are dropped.
    """
    from app.domains.graph.ids import public_id
    from app.domains.lighting.models import DmxStep, DmxUniverse, LightingFixture

    universes = (await db.scalars(select(DmxUniverse).where(DmxUniverse.job_id == job_id))).all()
    if not universes:
        return False
    by_public = {
        public_id(n): n
        for n in (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.kind == "dmx_universe"
                )
            )
        ).all()
    }
    by_ref = {
        d.legacy_ref: d
        for d in (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.legacy_ref.is_not(None)
                )
            )
        ).all()
    }
    fixture_node = {}
    for fixture in (
        await db.scalars(select(LightingFixture).where(LightingFixture.job_id == job_id))
    ).all():
        node = (
            by_ref.get(f"audio_devices:{fixture.device_id}") if fixture.device_id else None
        ) or by_ref.get(f"lighting_fixtures:{fixture.id}")
        if node is not None:
            fixture_node[fixture.id] = node

    def done(node: GraphDevice | None) -> bool:
        return node is not None and not node.legacy_ref and "legacy_id" in (node.attributes or {})

    changed = False
    for universe in universes:
        node = by_public.get(universe.id)
        if done(node):
            continue
        changed = True
        source = by_ref.get(f"audio_devices:{universe.source_device_id}")
        fresh = universe_node(
            job_id,
            universe.number,
            universe.name or "",
            universe.notes or "",
            {"device_id": str(source.id), "port": universe.source_port or ""} if source else None,
        )
        fresh.attributes = {**fresh.attributes, "legacy_id": str(universe.id)}
        if node is None:
            node = fresh
            db.add(node)
        else:  # a mirror node keeps its id; its content is taken from the row
            node.name, node.notes, node.position = fresh.name, fresh.notes, fresh.position
            node.attributes, node.ports, node.legacy_ref = fresh.attributes, fresh.ports, None
        await db.flush()
        for edge in (
            await db.scalars(
                select(ConnectionEdge).where(
                    ConnectionEdge.job_id == job_id, ConnectionEdge.signal == "dmx"
                )
            )
        ).all():
            ref = (edge.attributes or {}).get("legacy_ref") or ""
            if ref.startswith(("dmx_universes:", "dmx_steps:")) and (
                (edge.attributes or {}).get("chain") == str(node.id)
                or edge.dst_device_id == node.id
            ):
                await db.delete(edge)
        await db.flush()
        rows = (
            await db.scalars(
                select(DmxStep).where(DmxStep.universe_id == universe.id).order_by(DmxStep.position)
            )
        ).all()
        steps = []
        for row in rows:
            target = (
                fixture_node.get(row.fixture_id)
                if row.fixture_id
                else by_ref.get(f"audio_devices:{row.device_id}")
            )
            if target is None:
                continue
            steps.append(
                {
                    "step_id": str(row.id),
                    "position": row.position or 0,
                    "node_id": str(target.id),
                    "parent_id": str(row.parent_id) if row.parent_id else None,
                    **{key: getattr(row, key, "") or "" for key in STEP_KEYS},
                }
            )
        await rebuild(db, node, steps)
    if changed:
        await db.commit()
    return changed
