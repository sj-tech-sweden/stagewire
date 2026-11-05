"""Power nodes and their feeds on the graph (no legacy tables behind them).

A power node is stored on a *host* graph node, which carries ``attributes.power_id`` (the node's
public id: the legacy id for an imported node, a new uuid for a new one):

- a node that stands for a piece of gear (a breakout box) is hosted by the **device's own node**,
  so it is still one thing on the map; the power side is kept beside the device's attributes
  (``power_kind``, ``power_name``, ``power_notes``, ``power_position``);
- any other power node is a node of its own (domain ``power``, kind = source / distro / breakout /
  extension) whose name, notes, position and canvas position are the node's.

The settings the engine reads are attributes of the host: ``rating_amps``, ``active``, ``outputs``,
``venue_outlet_id``, ``venue_group_id`` (these names are what the web app has always read) plus
``feed_connector``, ``phase``, ``power_parent_id`` (the public id of the parent power node) and
``power_feeds`` (extra merged feeds: ``{feed_id, parent_id, feed_connector, phase, position}``).

The edges between hosts (signal ``power``, ``attributes.power_feed`` = ``"primary"`` or the feed
id, ``attributes.power_node`` = the fed node's public id) are rebuilt from those attributes by
``rebuild_feeds``. Loads (devices, fixtures, plot elements) plug in through their own
``power_node_id`` columns, which hold a power node's public id; the sync draws those edges.

``rigging.service`` reads nodes and feeds through ``load_nodes`` / ``load_feeds`` as objects
shaped like the old table rows, so the power engine (``rigging/router.py``, ``power_tree``) is
unchanged.
"""

import uuid
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.backfill import Backfill
from app.domains.graph.ids import power_id_of, public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice, scope_filter

POWER_KINDS = ("source", "distro", "breakout", "extension")
SETTINGS = ("rating_amps", "active", "outputs", "venue_outlet_id", "venue_group_id")


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


async def host_nodes(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> dict[uuid.UUID, GraphDevice]:
    """Every power node of the context: public power id -> its host node."""
    out: dict[uuid.UUID, GraphDevice] = {}
    for node in (
        await db.scalars(select(GraphDevice).where(scope_filter(GraphDevice, job_id, venue_id)))
    ).all():
        power_id = power_id_of(node)
        if power_id is not None:
            out[power_id] = node
    return out


def _hosted(host: GraphDevice) -> bool:
    """On a device's own node (it has its legacy device row), not a node made for the power."""
    return bool(host.legacy_ref and host.legacy_ref.startswith("device:"))


def node_view(power_id: uuid.UUID, host: GraphDevice) -> SimpleNamespace:
    """A power node shaped like the old ``PowerNode`` row."""
    a = host.attributes or {}
    hosted = _hosted(host)
    return SimpleNamespace(
        id=power_id,
        job_id=host.job_id,
        parent_id=_uuid(a.get("power_parent_id")),
        position=a.get("power_position", 0) if hosted else host.position,
        kind=a.get("power_kind", "distro") if hosted else host.kind,
        name=(a.get("power_name") or "") if hosted else host.name,
        feed_connector=a.get("feed_connector") or "",
        phase=a.get("phase"),
        outputs=a.get("outputs") or [],
        rating_amps=a.get("rating_amps"),
        active=a.get("active", True),
        venue_outlet_id=_uuid(a.get("venue_outlet_id")),
        venue_group_id=_uuid(a.get("venue_group_id")),
        device_id=public_id(host) if hosted else None,
        x_cm=None if hosted else host.canvas_x_cm,
        y_cm=None if hosted else host.canvas_y_cm,
        notes=(a.get("power_notes") or "") if hosted else (host.notes or ""),
    )


def feed_views(power_id: uuid.UUID, host: GraphDevice) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=uuid.UUID(f["feed_id"]),
            job_id=host.job_id,
            node_id=power_id,
            parent_id=uuid.UUID(f["parent_id"]),
            feed_connector=f.get("feed_connector") or "",
            phase=f.get("phase"),
            position=f.get("position", 0),
        )
        for f in (host.attributes or {}).get("power_feeds", [])
    ]


async def load_nodes(db: AsyncSession, job_id: uuid.UUID) -> list[SimpleNamespace]:
    views = [node_view(pid, host) for pid, host in (await host_nodes(db, job_id)).items()]
    return sorted(views, key=lambda v: (v.position, str(v.id)))


async def load_feeds(db: AsyncSession, job_id: uuid.UUID) -> list[SimpleNamespace]:
    out = []
    for pid, host in (await host_nodes(db, job_id)).items():
        out.extend(feed_views(pid, host))
    return sorted(out, key=lambda f: (f.position, str(f.id)))


async def get_node(
    db: AsyncSession, job_id: uuid.UUID, power_id: uuid.UUID
) -> SimpleNamespace | None:
    host = (await host_nodes(db, job_id)).get(power_id)
    return node_view(power_id, host) if host is not None else None


async def host_of(db: AsyncSession, job_id: uuid.UUID, power_id: uuid.UUID) -> GraphDevice | None:
    return (await host_nodes(db, job_id)).get(power_id)


async def find_by_setting(
    db: AsyncSession, job_id: uuid.UUID, key: str, value: uuid.UUID
) -> SimpleNamespace | None:
    """The power node whose ``venue_outlet_id`` / ``venue_group_id`` is ``value``."""
    for pid, host in (await host_nodes(db, job_id)).items():
        if (host.attributes or {}).get(key) == str(value):
            return node_view(pid, host)
    return None


def _settings(data: dict) -> dict:
    out = {}
    for key in SETTINGS:
        if key in data and data[key] is not None and data[key] != []:
            out[key] = str(data[key]) if key.startswith("venue_") else data[key]
    return out


async def create_node(db: AsyncSession, job_id: uuid.UUID, data: dict) -> SimpleNamespace:
    """Make a power node (the caller has validated it) and its feed edge."""
    power_id = uuid.uuid4()
    hosts = await host_nodes(db, job_id)
    position = len(hosts)
    common = {
        **_settings(data),
        "power_id": str(power_id),
        "feed_connector": data.get("feed_connector") or "",
        "phase": data.get("phase"),
        "power_parent_id": str(data["parent_id"]) if data.get("parent_id") else None,
        "power_feeds": [],
    }
    device_id = data.get("device_id")
    if device_id:
        host = next(
            (
                n
                for n in (
                    await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))
                ).all()
                if power_id_of(n) is None
                and (n.legacy_ref or "").startswith("device:")
                and public_id(n) == device_id
            ),
            None,
        )
        if host is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found")
        host.attributes = {
            **(host.attributes or {}),
            **common,
            "power_kind": data.get("kind", "distro"),
            "power_name": data.get("name") or data.get("kind", "distro"),
            "power_notes": data.get("notes") or "",
            "power_position": position,
        }
    else:
        host = GraphDevice(
            id=uuid.uuid4(),
            job_id=job_id,
            domain="power",
            kind=data.get("kind", "distro"),
            name=data.get("name") or data.get("kind", "distro"),
            notes=data.get("notes") or "",
            position=position,
            attributes=common,
            ports=[],
            canvas_x_cm=data.get("x_cm"),
            canvas_y_cm=data.get("y_cm"),
        )
        db.add(host)
    await db.flush()
    await rebuild_feeds(db, job_id)
    return node_view(power_id, host)


async def update_node(
    db: AsyncSession, job_id: uuid.UUID, power_id: uuid.UUID, data: dict
) -> SimpleNamespace:
    host = await host_of(db, job_id, power_id)
    if host is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Power node not found")
    attributes = dict(host.attributes or {})
    hosted = _hosted(host)
    for key in SETTINGS:
        if key in data:
            value = data[key]
            if value is None or value == []:
                attributes.pop(key, None)
            else:
                attributes[key] = str(value) if key.startswith("venue_") else value
    if "feed_connector" in data:
        attributes["feed_connector"] = data["feed_connector"] or ""
    if "phase" in data:
        attributes["phase"] = data["phase"]
    if "parent_id" in data:
        attributes["power_parent_id"] = str(data["parent_id"]) if data["parent_id"] else None
    if hosted:
        for key, attr in (
            ("name", "power_name"),
            ("notes", "power_notes"),
            ("kind", "power_kind"),
            ("position", "power_position"),
        ):
            if key in data and data[key] is not None:
                attributes[attr] = data[key]
    else:
        for key in ("name", "notes", "kind", "position"):
            if data.get(key) is not None:
                setattr(host, key, data[key])
        if "x_cm" in data:
            host.canvas_x_cm = data["x_cm"]
        if "y_cm" in data:
            host.canvas_y_cm = data["y_cm"]
    host.attributes = attributes
    await db.flush()
    await rebuild_feeds(db, job_id)
    return node_view(power_id, host)


async def delete_node(db: AsyncSession, job_id: uuid.UUID, power_id: uuid.UUID) -> None:
    host = await host_of(db, job_id, power_id)
    if host is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Power node not found")
    if _hosted(host):  # the device stays; only its power side goes
        drop = {
            "power_id",
            "power_kind",
            "power_name",
            "power_notes",
            "power_position",
            "power_feeds",
            "power_parent_id",
            "feed_connector",
            "phase",
            *SETTINGS,
        }
        host.attributes = {k: v for k, v in (host.attributes or {}).items() if k not in drop}
    else:
        for edge in (
            await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))
        ).all():
            if host.id in (edge.src_device_id, edge.dst_device_id):
                await db.delete(edge)
        await db.delete(host)
    await db.flush()
    await rebuild_feeds(db, job_id)


async def add_feed(
    db: AsyncSession, job_id: uuid.UUID, power_id: uuid.UUID, parent_id: uuid.UUID, data: dict
) -> SimpleNamespace:
    host = await host_of(db, job_id, power_id)
    feeds = list((host.attributes or {}).get("power_feeds", []))
    feed = {
        "feed_id": str(uuid.uuid4()),
        "parent_id": str(parent_id),
        "feed_connector": data.get("feed_connector") or "",
        "phase": data.get("phase"),
        "position": len(await load_feeds(db, job_id)),
    }
    host.attributes = {**host.attributes, "power_feeds": [*feeds, feed]}
    await db.flush()
    await rebuild_feeds(db, job_id)
    return next(f for f in feed_views(power_id, host) if str(f.id) == feed["feed_id"])


async def update_feed(
    db: AsyncSession, job_id: uuid.UUID, feed_id: uuid.UUID, changes: dict
) -> bool:
    for host in (await host_nodes(db, job_id)).values():
        feeds = host.attributes.get("power_feeds", [])
        if any(f["feed_id"] == str(feed_id) for f in feeds):
            host.attributes = {
                **host.attributes,
                "power_feeds": [
                    {**f, **changes} if f["feed_id"] == str(feed_id) else f for f in feeds
                ],
            }
            await db.flush()
            await rebuild_feeds(db, job_id)
            return True
    return False


async def remove_feed(db: AsyncSession, job_id: uuid.UUID, feed_id: uuid.UUID) -> bool:
    for host in (await host_nodes(db, job_id)).values():
        feeds = host.attributes.get("power_feeds", [])
        if any(f["feed_id"] == str(feed_id) for f in feeds):
            host.attributes = {
                **host.attributes,
                "power_feeds": [f for f in feeds if f["feed_id"] != str(feed_id)],
            }
            await db.flush()
            await rebuild_feeds(db, job_id)
            return True
    return False


async def rebuild_feeds(db: AsyncSession, job_id: uuid.UUID) -> None:
    """Make the job's feed edges match the hosts' attributes, and make their ports.

    Existing edges are kept (same id) when their parent, child and feed are unchanged, so an
    open workspace is not handed new ids on every sync; missing ones are made, stale ones removed.
    """
    hosts = await host_nodes(db, job_id)
    wanted: dict[tuple, dict] = {}

    def want(parent_id, child_id, connector, phase, marker) -> None:
        parent, child = hosts.get(parent_id), hosts.get(child_id)
        if parent is None or child is None or parent.id == child.id:
            return
        wanted[(parent.id, child.id, marker)] = {
            "parent": parent,
            "child": child,
            "connector": connector,
            "phase": phase if phase in ("L1", "L2", "L3") else None,
            "power_node": str(child_id),
        }

    for pid, host in hosts.items():
        a = host.attributes or {}
        if a.get("power_parent_id"):
            want(
                _uuid(a["power_parent_id"]),
                pid,
                a.get("feed_connector") or "",
                a.get("phase"),
                "primary",
            )
        for feed in a.get("power_feeds", []):
            want(
                uuid.UUID(feed["parent_id"]),
                pid,
                feed.get("feed_connector") or "",
                feed.get("phase"),
                feed["feed_id"],
            )

    existing: dict[tuple, ConnectionEdge] = {}
    for edge in (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == job_id, ConnectionEdge.signal == "power"
            )
        )
    ).all():
        marker = (edge.attributes or {}).get("power_feed")
        if marker is None:
            continue  # a load's edge, drawn by the sync
        key = (edge.src_device_id, edge.dst_device_id, marker)
        if key in wanted and key not in existing:
            existing[key] = edge
        else:
            await db.delete(edge)
    for key, spec in wanted.items():
        parent, child = spec["parent"], spec["child"]
        src_port = Backfill.port(parent, "out", "power", spec["connector"])
        dst_port = Backfill.port(child, "in", "power", spec["connector"])
        attributes = {
            "connector": spec["connector"],
            "power_feed": key[2],
            "power_node": spec["power_node"],
        }
        edge = existing.get(key)
        if edge is None:
            db.add(
                ConnectionEdge(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    signal="power",
                    src_device_id=parent.id,
                    src_port=src_port,
                    dst_device_id=child.id,
                    dst_port=dst_port,
                    channels=1,
                    phase=spec["phase"],
                    attributes=attributes,
                )
            )
        elif (
            edge.src_port,
            edge.dst_port,
            edge.phase,
            edge.attributes.get("connector"),
        ) != (src_port, dst_port, spec["phase"], spec["connector"]):
            edge.src_port, edge.dst_port, edge.phase = src_port, dst_port, spec["phase"]
            edge.attributes = {**edge.attributes, **attributes}
    await db.flush()


# ---- edits that come in through the graph API -------------------------------------------------


async def after_patch(db: AsyncSession, job_id: uuid.UUID, node: GraphDevice, data: dict) -> None:
    """A PATCH of a node that hosts a power node: run the power rules on what it changed.

    The PATCH is already applied to the node; the engine checks the whole tree with it (a 422 says
    what is wrong and the PATCH is rolled back) and keeps its own derived data in step.
    """
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    power_id = power_id_of(node)
    if power_id is None:
        return
    sent = data.get("attributes") or {}
    changes = {
        key: sent[key]
        for key in ("rating_amps", "active", "outputs")
        if key in sent and not (sent[key] is None and key != "rating_amps")
    }
    if not _hosted(node):
        for key in ("name", "notes", "kind"):
            if data.get(key) is not None and key in rigging_schemas.PowerNodeUpdate.model_fields:
                changes[key] = data[key]
    if not changes:
        return
    try:
        await rigging_router.update_node(
            job_id, power_id, rigging_schemas.PowerNodeUpdate(**changes), db
        )
    except HTTPException:
        await db.rollback()
        raise


async def check_deletable(db: AsyncSession, job_id: uuid.UUID, power_id: uuid.UUID) -> None:
    """The engine's rules for removing a power node: nothing may hang from it or be plugged in."""
    from app.domains.rigging import service as rigging_service

    nodes = await load_nodes(db, job_id)
    feeds = await load_feeds(db, job_id)
    if any(n.parent_id == power_id for n in nodes) or any(f.parent_id == power_id for f in feeds):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Move or remove the nodes fed from this one first"
        )
    if any(
        r.power_node_id == str(power_id) for r in await rigging_service.collect_loads(db, job_id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Unplug the loads on this node first")


async def edge_patch(db: AsyncSession, job_id: uuid.UUID, edge: ConnectionEdge, data: dict) -> bool:
    """A PATCH of a feed edge's connector or phase is a change to the feed."""
    from app.domains.rigging import power_tree
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas
    from app.domains.rigging import service as rigging_service

    marker = (edge.attributes or {}).get("power_feed")
    if edge.signal != "power" or marker is None:
        return False
    connector = (data.get("attributes") or {}).get("connector")
    changes: dict = {}
    if connector is not None:
        changes["feed_connector"] = connector
    if "phase" in data:
        changes["phase"] = data["phase"]
    if not changes:
        return False
    child = uuid.UUID(edge.attributes["power_node"])
    try:
        if marker == "primary":
            await rigging_router.update_node(
                job_id, child, rigging_schemas.PowerNodeUpdate(**changes), db
            )
        else:
            feed_id = uuid.UUID(marker)
            nodes = await rigging_service.list_nodes(db, job_id)
            feeds = [
                SimpleNamespace(**{**vars(f), **changes}) if f.id == feed_id else f
                for f in await rigging_service.list_feeds(db, job_id)
            ]
            rows = await rigging_service.collect_loads(db, job_id)
            evaluation = power_tree.evaluate(
                rigging_service.to_tree_nodes(nodes, feeds), rigging_service.to_tree_loads(rows)
            )
            feed = next(f for f in feeds if f.id == feed_id)
            names = [n.name for n in nodes if n.id in (feed.node_id, feed.parent_id)]
            await rigging_router._reject(rigging_router._problems(evaluation, *names))
            await update_feed(db, job_id, feed_id, changes)
    except HTTPException:
        await db.rollback()
        raise
    return True


async def edge_delete(db: AsyncSession, job_id: uuid.UUID, edge: ConnectionEdge) -> bool:
    """Deleting an extra feed removes it; a node's own feed cannot be cut here."""
    marker = (edge.attributes or {}).get("power_feed")
    if edge.signal != "power" or marker is None:
        return False
    if marker == "primary":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A node's own feed cannot be cut; move the node to another parent or delete it",
        )
    await remove_feed(db, job_id, uuid.UUID(marker))
    return True
