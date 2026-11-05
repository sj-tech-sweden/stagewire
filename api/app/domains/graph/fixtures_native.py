"""Lighting fixtures on the graph (no legacy table behind them).

A fixture is stored on a *host* graph node that carries ``attributes.fixture_id`` (the fixture's
public id: the legacy id for an imported fixture, a new uuid for a new one):

- the first fixture of a piece of gear is hosted by the **device's own node**, so it is one thing
  on the map and in the lists;
- any other fixture (none, or a further one on a device that already has one) is a node of its own
  (domain ``lighting``, kind ``fixture``); a further one remembers its device in
  ``attributes.fixture_device_id``.

The fixture's settings are attributes of the host, under the names the web app has always read:
``universe``, ``dmx_address``, ``fixture_type``, ``channel_mode``, ``footprint``, ``location``,
``gel``, ``purpose``, and its load links ``rigging_point_id`` / ``power_node_id`` (the *graph node*
ids of the point and of the power host) and ``power_connector``. What is not shown there is kept as
``fixture_notes``, ``fixture_position``, ``import_batch_id``, ``fixture_type_id`` and
``fixture_mode_id``. For a device host the node's own name and notes stay the device's.

``lighting.service`` reads fixtures through ``load_fixtures`` as objects shaped like the old rows
(public ids for the point and the power node, as the power engine uses them), so the rest of the
lighting and power code is unchanged. A fixture plugged into a power node has a power edge from
that node (``attributes.fixture_power`` = the fixture's public id), kept by ``sync_power_edges``.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph import dmx_native, power_native
from app.domains.graph.backfill import Backfill
from app.domains.graph.ids import public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice, scope_filter

SETTING_KEYS = (
    "universe",
    "dmx_address",
    "fixture_type",
    "channel_mode",
    "footprint",
    "location",
    "gel",
    "purpose",
)
EXTRA_KEYS = ("fixture_type_id", "fixture_mode_id", "import_batch_id")
TEXT_KEYS = ("fixture_type", "channel_mode", "location", "gel", "purpose")
ALL_ATTRS = (
    *SETTING_KEYS,
    "fixture_id",
    "fixture_notes",
    "fixture_position",
    "rigging_point_id",
    "power_node_id",
    "power_connector",
    *EXTRA_KEYS,
)


def fixture_id_of(node: GraphDevice) -> uuid.UUID | None:
    raw = (node.attributes or {}).get("fixture_id")
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _hosted(host: GraphDevice) -> bool:
    """On a device's own node (which has its legacy device row), not a node made for the fixture."""
    return bool(host.legacy_ref and host.legacy_ref.startswith("device:"))


async def host_nodes(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> dict[uuid.UUID, GraphDevice]:
    out: dict[uuid.UUID, GraphDevice] = {}
    for node in (
        await db.scalars(select(GraphDevice).where(scope_filter(GraphDevice, job_id, venue_id)))
    ).all():
        fid = fixture_id_of(node)
        if fid is not None:
            out[fid] = node
    return out


def fixture_view(
    fid: uuid.UUID, host: GraphDevice, point_ids: dict, power_ids: dict
) -> SimpleNamespace:
    """A fixture shaped like the old ``LightingFixture`` row (point and node as public ids)."""
    a = host.attributes or {}
    text = {k: a.get(k) or "" for k in TEXT_KEYS}
    return SimpleNamespace(
        id=fid,
        job_id=host.job_id,
        position=a.get("fixture_position", 0),
        device_id=public_id(host) if _hosted(host) else _uuid(a.get("fixture_device_id")),
        universe=a.get("universe"),
        dmx_address=a.get("dmx_address"),
        footprint=a.get("footprint"),
        notes=a.get("fixture_notes") or "",
        import_batch_id=_uuid(a.get("import_batch_id")),
        fixture_type_id=_uuid(a.get("fixture_type_id")),
        fixture_mode_id=_uuid(a.get("fixture_mode_id")),
        rigging_point_id=point_ids.get(a.get("rigging_point_id")),
        power_node_id=power_ids.get(a.get("power_node_id")),
        power_connector=a.get("power_connector") or "",
        created_at=host.created_at or datetime.min,
        **text,
    )


async def _id_maps(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> tuple[dict, dict]:
    """Graph node id (as the attributes hold it) -> public id, for points and power nodes."""
    points = {
        str(n.id): public_id(n)
        for n in (
            await db.scalars(
                select(GraphDevice).where(
                    scope_filter(GraphDevice, job_id, venue_id),
                    GraphDevice.kind == "rigging_point",
                )
            )
        ).all()
    }
    power = {
        str(h.id): pid for pid, h in (await power_native.host_nodes(db, job_id, venue_id)).items()
    }
    return points, power


async def load_fixtures(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> list[SimpleNamespace]:
    points, power = await _id_maps(db, job_id, venue_id)
    views = [
        fixture_view(fid, h, points, power)
        for fid, h in (await host_nodes(db, job_id, venue_id)).items()
    ]
    return sorted(views, key=lambda f: (f.position, f.created_at, str(f.id)))


async def get_fixture(
    db: AsyncSession, job_id: uuid.UUID, fixture_id: uuid.UUID
) -> SimpleNamespace | None:
    return next((f for f in await load_fixtures(db, job_id) if f.id == fixture_id), None)


async def host_of(db: AsyncSession, job_id: uuid.UUID, fixture_id: uuid.UUID) -> GraphDevice | None:
    return (await host_nodes(db, job_id)).get(fixture_id)


async def _graph_ids(db: AsyncSession, job_id: uuid.UUID, data: dict) -> dict:
    """The point and power node a caller names by public id, as the host's graph node ids."""
    out: dict = {}
    if "rigging_point_id" in data:
        point = data["rigging_point_id"]
        node = next(
            (
                n
                for n in (
                    await db.scalars(
                        select(GraphDevice).where(
                            GraphDevice.job_id == job_id, GraphDevice.kind == "rigging_point"
                        )
                    )
                ).all()
                if public_id(n) == point
            ),
            None,
        )
        out["rigging_point_id"] = str(node.id) if node and point else None
    if "power_node_id" in data:
        host = (
            await power_native.host_of(db, job_id, data["power_node_id"])
            if data["power_node_id"]
            else None
        )
        out["power_node_id"] = str(host.id) if host else None
    return out


def _apply(attributes: dict, data: dict, graph_ids: dict) -> dict:
    attributes = dict(attributes)
    for key in SETTING_KEYS:
        if key in data:
            value = data[key]
            if value in (None, "") and key not in TEXT_KEYS:
                attributes.pop(key, None)
            elif value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
    for key in EXTRA_KEYS:
        if key in data:
            if data[key] is None:
                attributes.pop(key, None)
            else:
                attributes[key] = str(data[key])
    if "notes" in data:
        attributes["fixture_notes"] = data["notes"] or ""
    if "power_connector" in data:
        attributes["power_connector"] = data["power_connector"] or ""
    for key, value in graph_ids.items():
        if value is None:
            attributes.pop(key, None)
        else:
            attributes[key] = value
    if not attributes.get("power_node_id"):
        attributes.pop("power_connector", None)
    return attributes


async def create_fixture(db: AsyncSession, job_id: uuid.UUID, data: dict) -> SimpleNamespace:
    """Make a fixture from cleaned data (``device_id`` = a device's public id or None)."""
    fid = uuid.uuid4()
    graph_ids = await _graph_ids(db, job_id, data)
    position = data.pop("position", None)
    if position is None:
        position = len(await host_nodes(db, job_id))
    device_id = data.get("device_id")
    attributes = _apply({"fixture_id": str(fid), "fixture_position": position}, data, graph_ids)
    host = None
    if device_id:
        host = next(
            (
                n
                for n in (
                    await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))
                ).all()
                if (n.legacy_ref or "").startswith("device:") and public_id(n) == device_id
            ),
            None,
        )
        if host is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found")
    if host is not None and fixture_id_of(host) is None:
        host.attributes = {**(host.attributes or {}), **attributes}
    else:
        if host is not None:  # a further fixture on a device that already carries one
            attributes["fixture_device_id"] = str(device_id)
        host = GraphDevice(
            id=uuid.uuid4(),
            job_id=job_id,
            domain="lighting",
            kind="fixture",
            name=data.get("purpose") or data.get("fixture_type") or "Fixture",
            notes=data.get("notes") or "",
            position=position,
            attributes=attributes,
            ports=[],
        )
        db.add(host)
    await db.flush()
    await sync_power_edges(db, job_id)
    points, power = await _id_maps(db, job_id)
    return fixture_view(fid, host, points, power)


async def update_fixture(
    db: AsyncSession, job_id: uuid.UUID, fixture_id: uuid.UUID, data: dict
) -> SimpleNamespace:
    host = await host_of(db, job_id, fixture_id)
    if host is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")
    graph_ids = await _graph_ids(db, job_id, data)
    host.attributes = _apply(host.attributes or {}, data, graph_ids)
    if not _hosted(host):
        host.name = data.get("purpose") or host.attributes.get("fixture_type") or host.name
        if "notes" in data:
            host.notes = data["notes"] or ""
    await db.flush()
    await sync_power_edges(db, job_id)
    points, power = await _id_maps(db, job_id)
    return fixture_view(fixture_id, host, points, power)


async def delete_fixture(db: AsyncSession, job_id: uuid.UUID, fixture_id: uuid.UUID) -> None:
    host = await host_of(db, job_id, fixture_id)
    if host is None:
        return
    await dmx_native.drop_node(db, job_id, host.id)  # its steps go (the fixture cascade)
    if _hosted(host):  # the device stays; only its fixture side goes
        host.attributes = {k: v for k, v in (host.attributes or {}).items() if k not in ALL_ATTRS}
    else:
        for edge in (
            await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))
        ).all():
            if host.id in (edge.src_device_id, edge.dst_device_id):
                await db.delete(edge)
        await db.delete(host)
    await db.flush()
    await sync_power_edges(db, job_id)


async def sync_power_edges(db: AsyncSession, job_id: uuid.UUID) -> None:
    """Keep one power edge from the fed power node to each plugged fixture (diff, no churn)."""
    hosts = await host_nodes(db, job_id)
    nodes = {str(n.id): n for n in hosts.values()}
    power_hosts = {str(h.id): h for h in (await power_native.host_nodes(db, job_id)).values()}
    wanted = {}
    for fid, host in hosts.items():
        feeder = power_hosts.get((host.attributes or {}).get("power_node_id"))
        if feeder is not None and feeder.id != host.id:
            wanted[fid] = (feeder, host, (host.attributes or {}).get("power_connector") or "")
    existing: dict[uuid.UUID, ConnectionEdge] = {}
    for edge in (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == job_id, ConnectionEdge.signal == "power"
            )
        )
    ).all():
        marker = _uuid((edge.attributes or {}).get("fixture_power"))
        if marker is None:
            continue
        spec = wanted.get(marker)
        if spec is not None and marker not in existing and spec[0].id == edge.src_device_id:
            existing[marker] = edge
        else:
            await db.delete(edge)
    del nodes
    for fid, (feeder, host, connector) in wanted.items():
        src_port = Backfill.port(feeder, "out", "power", connector)
        dst_port = Backfill.port(host, "in", "power", connector)
        edge = existing.get(fid)
        attributes = {"connector": connector, "fixture_power": str(fid)}
        if edge is None:
            db.add(
                ConnectionEdge(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    signal="power",
                    src_device_id=feeder.id,
                    src_port=src_port,
                    dst_device_id=host.id,
                    dst_port=dst_port,
                    channels=1,
                    attributes=attributes,
                )
            )
        elif (edge.src_port, edge.dst_port, edge.attributes.get("connector")) != (
            src_port,
            dst_port,
            connector,
        ):
            edge.src_port, edge.dst_port = src_port, dst_port
            edge.attributes = {**edge.attributes, **attributes}
    await db.flush()


async def edge_patch(db: AsyncSession, job_id: uuid.UUID, edge: ConnectionEdge, data: dict) -> bool:
    """A PATCH of a fixture's power edge connector is the fixture's power connector."""
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    fid = _uuid((edge.attributes or {}).get("fixture_power"))
    connector = (data.get("attributes") or {}).get("connector")
    if edge.signal != "power" or fid is None or connector is None:
        return False
    try:
        await rigging_router.assign_load(
            job_id, "fixture", fid, rigging_schemas.LoadAssign(power_connector=connector), db
        )
    except HTTPException:
        await db.rollback()
        raise
    return True


async def edge_delete(db: AsyncSession, job_id: uuid.UUID, edge: ConnectionEdge) -> bool:
    """Deleting a fixture's power edge unplugs it."""
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    fid = _uuid((edge.attributes or {}).get("fixture_power"))
    if edge.signal != "power" or fid is None:
        return False
    await rigging_router.assign_load(
        job_id, "fixture", fid, rigging_schemas.LoadAssign(power_node_id=None), db
    )
    return True


async def after_patch(db: AsyncSession, job_id: uuid.UUID, node: GraphDevice, data: dict) -> None:
    """A PATCH of a node that hosts a fixture: apply the library rules to what it changed.

    The PATCH is already on the node; the fixture service re-applies it through the type/mode rules
    (a chosen mode sets the footprint) and the device defaults, as an edit of the fixture would.
    """
    from app.domains.graph.mirror import _fixture_changes
    from app.domains.lighting import service as lighting_service

    fid = fixture_id_of(node)
    if fid is None:
        return
    changes = _fixture_changes(data)
    if not changes:
        return
    fixture = await get_fixture(db, job_id, fid)
    try:
        await lighting_service.update_fixture(db, job_id, fixture, changes)
    except HTTPException:
        await db.rollback()
        raise
