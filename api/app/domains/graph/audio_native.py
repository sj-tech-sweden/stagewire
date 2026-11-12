"""Channel lists, channels, outputs and their patch points on the graph (no legacy tables).

Nodes (no ``legacy_ref``; the public id, ``ids.public_id``, is the legacy id of an imported row and
the node id of a new one, so plot links, cable routes and a device's ``sound_list_id`` keep
working):

- ``channel_list`` (domain ``audio``): name, position and the mixer attributes
  (``mixer_product_id`` / ``mixer_product_name`` / ``mixer_inputs`` / ``mixer_buses``; the product
  is also the node's Stockwire product);
- ``channel``: ``attributes.list_id`` (node id of the list), ``channel_list_id`` (its public id),
  ``source_label`` (as typed; the node name falls back to "Ch N"), ``channel_number`` (also the
  node position), the other channel fields under their old names, ``points`` = its patch chain;
- ``output``: the same for a bus, with ``mode`` / ``connector`` / ``color_code`` and ``points``.

A patch point is a dict in the node's ``points``: ``point_id`` (legacy id or a new uuid),
``position``, ``point_type``, ``connector``, ``patch_label``, ``notes``, ``device_id`` (the
*node id* of the device), ``revision`` (the point's own, for the legacy API's optimistic writes)
and, for an output, ``parent_id`` (a point id), ``parallel`` and ``bus_connector``.

The edges the web app draws (devices -> channel, console -> bus -> devices) are derived from the
points by ``sync_edges``, run by every sync through the sync's ``edge()`` so they keep their ids and
are pruned like every mirrored edge; the legacy ids in the edge refs are the point ids. A channel's
selected source is also a derived edge, so source and patch-chain edits share one graph path.

The ``*_row`` functions return objects shaped like the old ORM rows (with ``patch_points`` /
``points`` / ``channels`` / ``outputs`` nested), so the audio service, router, exports and reports
are unchanged. ``device_id`` in a row is the device's
public id, in a point the device's node id.
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.wwb import normalize_wireless_attributes
from app.domains.graph import devices_native, plot_native
from app.domains.graph.backfill import FAN_OUT, _point_attrs
from app.domains.graph.ids import public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice

LIST, CHANNEL, OUTPUT = "channel_list", "channel", "output"
KINDS = (LIST, CHANNEL, OUTPUT)
LIST_ATTRS = ("mixer_product_id", "mixer_product_name", "mixer_inputs", "mixer_buses")
CHANNEL_ATTRS = (
    "channel_number",
    "input_type",
    "mixer_input",
    "device",
    "stand_type",
    "instrument_group",
    "performer_name",
    "wireless_pack",
    "wireless_frequency_mhz",
    "wireless_group",
    "wireless_channel",
    "phantom_power",
    "stereo",
    "stereo_channel",
    "color_code",
    "stockwire_asset_id",
    "stand_product_id",
    "stand_product_name",
)
OUTPUT_ATTRS = ("mode", "connector", "color_code")
# A channel is the logical endpoint of a source signal: a mic or a digital stagebox feeds *into*
# the channel (`in`), and the channel then feeds *out* to a bus / PA (`out`). These two ports are
# fixed for every channel, so they are derived rather than trusted from the stored `ports` column:
# older channels created before the `in` port existed only stored `out`, and would otherwise fail
# edge validation ("no port 'in'") even though the channel is a valid endpoint.
CHANNEL_PORTS = (
    {"id": "in", "direction": "in", "signal": "audio"},
    {"id": "out", "direction": "out", "signal": "audio"},
)


def normalize_channel_ports(ports: list | None) -> list:
    """Return the channel's ports with `in` and `out` guaranteed present (idempotent)."""
    have = {p.get("id") for p in (ports or [])}
    merged = list(ports or [])
    for canon in CHANNEL_PORTS:
        if canon["id"] not in have:
            merged.append(dict(canon))
    return merged


CHANNEL_DEFAULTS = {
    "stand_type": "",
    "instrument_group": "other",
    "phantom_power": False,
    "stereo": False,
}
OUTPUT_DEFAULTS = {"mode": "mono"}
# a null in an edit clears only these (the rest of the old columns were NOT NULL: null = not sent)
CLEARABLE = {
    "stockwire_product_id",
    "stockwire_product_name",
    "stand_product_id",
    "stand_product_name",
    "mixer_product_id",
    "mixer_product_name",
    "mixer_inputs",
    "mixer_buses",
    "device",
}
POINT_KEYS = ("connector", "patch_label", "notes")
POINT_TEXT = ("point_type", "connector", "patch_label", "notes")


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _age(node: GraphDevice) -> tuple[float, str]:
    return (node.created_at.timestamp() if node.created_at else 0.0, str(node.id))


async def job_nodes(db: AsyncSession, job_id: uuid.UUID) -> list[GraphDevice]:
    return list((await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))).all())


def _of_kind(nodes: list[GraphDevice], kind: str) -> list[GraphDevice]:
    return [n for n in nodes if n.kind == kind and not n.legacy_ref]


def is_native(node: GraphDevice | None) -> bool:
    return node is not None and node.kind in KINDS and not node.legacy_ref


def _native(node: GraphDevice | None, kind: str) -> bool:
    return node is not None and node.kind == kind and not node.legacy_ref


def _device_public(nodes: list[GraphDevice]) -> dict[uuid.UUID, uuid.UUID]:
    """Device node id -> the device's public id (the id in its ``device:`` ref)."""
    return {
        n.id: public_id(n) for n in nodes if n.legacy_ref and n.legacy_ref.startswith("device:")
    }


async def find_node(
    db: AsyncSession,
    kind: str,
    ident: uuid.UUID,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
) -> GraphDevice | None:
    """The native node of ``kind`` whose public id is ``ident`` (a node id or an imported id).

    Scoped by ``job_id`` (a job graph) or ``venue_id`` (a venue Standard Base Rig). When neither
    is given the job_id on the resolved node is not checked (legacy cross-job lookup).
    """
    node = await db.get(GraphDevice, ident)
    scoped = node is not None and (
        (job_id is None and venue_id is None)
        or (job_id is not None and node.job_id == job_id)
        or (venue_id is not None and node.venue_id == venue_id)
    )
    if _native(node, kind) and scoped:
        return node
    query = select(GraphDevice).where(GraphDevice.kind == kind, GraphDevice.legacy_ref.is_(None))
    if job_id is not None:
        query = query.where(GraphDevice.job_id == job_id)
    if venue_id is not None:
        query = query.where(GraphDevice.venue_id == venue_id)
    query = query.where(GraphDevice.attributes["legacy_id"].as_string() == str(ident))
    return (await db.scalars(query)).first()


async def device_node(
    db: AsyncSession, job_id: uuid.UUID, device_id: uuid.UUID
) -> GraphDevice | None:
    """The graph node of a device row (made by a sync, which every legacy write triggers)."""
    query = select(GraphDevice).where(
        GraphDevice.job_id == job_id, GraphDevice.legacy_ref == f"device:{device_id}"
    )
    return (await db.scalars(query)).first()


# --- row shapes --------------------------------------------------------------------------------


def point_row(point: dict, owner: GraphDevice, devices: dict) -> SimpleNamespace:
    """A patch point shaped like ``ChannelPatchPoint`` / ``OutputPatchPoint``."""
    row = SimpleNamespace(
        id=_uuid(point["point_id"]),
        position=point.get("position") or 0,
        point_type=point.get("point_type") or "mixer",
        connector=point.get("connector") or "",
        patch_label=point.get("patch_label") or "",
        notes=point.get("notes") or "",
        device_id=devices.get(_uuid(point.get("device_id"))),
        revision=point.get("revision") or 1,
    )
    if owner.kind == CHANNEL:
        row.channel_id = public_id(owner)
    else:
        row.output_id = public_id(owner)
        row.parallel = bool(point.get("parallel"))
        row.parent_id = _uuid(point.get("parent_id"))
        row.bus_connector = point.get("bus_connector")
    return row


def _points(node: GraphDevice, devices: dict) -> list[SimpleNamespace]:
    # a stable sort: points that share a position keep the order they were added in
    ordered = sorted(
        (node.attributes or {}).get("points", []), key=lambda p: p.get("position") or 0
    )
    return [point_row(p, node, devices) for p in ordered]


def channel_row(node: GraphDevice, devices: dict) -> SimpleNamespace:
    a = {**CHANNEL_DEFAULTS, **(node.attributes or {})}
    # fold the structured MHz (or a legacy free-text ``wireless_frequency`` string) into
    # the read model so unmigrated rows still expose ``wireless_frequency_mhz``
    a = {**a, **normalize_wireless_attributes(a)}
    return SimpleNamespace(
        id=public_id(node),
        job_id=node.job_id,
        channel_list_id=_uuid(a.get("channel_list_id")),
        source_label=a.get("source_label") or "",
        notes=node.notes or "",
        stockwire_product_id=node.stockwire_product_id,
        stockwire_product_name=node.stockwire_product_name,
        revision=node.revision,
        created_at=node.created_at,
        patch_points=_points(node, devices),
        **{key: a.get(key, CHANNEL_DEFAULTS.get(key)) for key in CHANNEL_ATTRS},
    )


def output_row(node: GraphDevice, devices: dict) -> SimpleNamespace:
    a = node.attributes or {}
    return SimpleNamespace(
        id=public_id(node),
        job_id=node.job_id,
        channel_list_id=_uuid(a.get("channel_list_id")),
        name=node.name,
        position=node.position,
        notes=node.notes or "",
        revision=node.revision,
        points=_points(node, devices),
        **{key: a.get(key, OUTPUT_DEFAULTS.get(key)) for key in OUTPUT_ATTRS},
    )


def list_row(node: GraphDevice, members: list[GraphDevice], devices: dict) -> SimpleNamespace:
    a = node.attributes or {}
    mine = str(node.id)
    channels = sorted(
        (channel_row(m, devices) for m in members if m.kind == CHANNEL and _list_of(m) == mine),
        key=lambda c: c.channel_number or 0,
    )
    outputs = sorted(
        (
            (m.position, _age(m), output_row(m, devices))
            for m in members
            if m.kind == OUTPUT and _list_of(m) == mine
        ),
        key=lambda t: t[:2],
    )
    return SimpleNamespace(
        id=public_id(node),
        job_id=node.job_id,
        name=node.name,
        position=node.position,
        created_at=node.created_at,
        channels=channels,
        outputs=[o for _, _, o in outputs],
        **{key: a.get(key) for key in LIST_ATTRS},
    )


def _list_of(node: GraphDevice) -> str | None:
    return (node.attributes or {}).get("list_id")


async def load_lists(db: AsyncSession, job_id: uuid.UUID) -> list[SimpleNamespace]:
    """The job's channel lists, each with its channels and outputs and their points."""
    nodes = await job_nodes(db, job_id)
    devices = _device_public(nodes)
    members = [n for n in nodes if n.kind in (CHANNEL, OUTPUT) and not n.legacy_ref]
    lists = sorted(_of_kind(nodes, LIST), key=lambda n: (n.position, _age(n)))
    return [list_row(n, members, devices) for n in lists]


async def get_list(
    db: AsyncSession, list_id: uuid.UUID, job_id: uuid.UUID | None = None
) -> SimpleNamespace | None:
    node = await find_node(db, LIST, list_id, job_id)
    if node is None:
        return None
    nodes = await job_nodes(db, node.job_id)
    return list_row(node, [n for n in nodes if n.kind in (CHANNEL, OUTPUT)], _device_public(nodes))


async def _row(db: AsyncSession, kind: str, node: GraphDevice | None):
    if node is None:
        return None
    devices = _device_public(await job_nodes(db, node.job_id))
    return (channel_row if kind == CHANNEL else output_row)(node, devices)


async def get_channel(
    db: AsyncSession, channel_id: uuid.UUID, job_id: uuid.UUID | None = None
) -> SimpleNamespace | None:
    return await _row(db, CHANNEL, await find_node(db, CHANNEL, channel_id, job_id))


async def get_output(
    db: AsyncSession, output_id: uuid.UUID, job_id: uuid.UUID | None = None
) -> SimpleNamespace | None:
    return await _row(db, OUTPUT, await find_node(db, OUTPUT, output_id, job_id))


async def list_channels(db: AsyncSession, list_id: uuid.UUID) -> list[SimpleNamespace]:
    found = await get_list(db, list_id)
    return found.channels if found else []


async def job_channels(db: AsyncSession, job_id: uuid.UUID) -> list[SimpleNamespace]:
    lists = await load_lists(db, job_id)
    return sorted((c for lst in lists for c in lst.channels), key=lambda c: c.channel_number or 0)


async def find_point(
    db: AsyncSession, kind: str, owner_id: uuid.UUID, point_id: uuid.UUID
) -> tuple[GraphDevice, dict] | None:
    node = await find_node(db, kind, owner_id)
    point = (
        next(
            (
                p
                for p in (node.attributes or {}).get("points", [])
                if p["point_id"] == str(point_id)
            ),
            None,
        )
        if node
        else None
    )
    return (node, point) if point else None


async def get_point(
    db: AsyncSession, kind: str, owner_id: uuid.UUID, point_id: uuid.UUID
) -> SimpleNamespace | None:
    found = await find_point(db, kind, owner_id, point_id)
    if found is None:
        return None
    node, point = found
    return point_row(point, node, _device_public(await job_nodes(db, node.job_id)))


async def totals(db: AsyncSession, job_id: uuid.UUID) -> tuple[int, int]:
    nodes = await job_nodes(db, job_id)
    return len(_of_kind(nodes, CHANNEL)), len(_of_kind(nodes, OUTPUT))


async def list_totals(db: AsyncSession, list_id: uuid.UUID) -> tuple[int, int]:
    found = await get_list(db, list_id)
    return (len(found.channels), len(found.outputs)) if found else (0, 0)


async def device_point_counts(db: AsyncSession, job_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Channel patch points per device (public id), for the device list's patch-point count."""
    nodes = await job_nodes(db, job_id)
    devices = _device_public(nodes)
    counts: dict[uuid.UUID, int] = {}
    for node in _of_kind(nodes, CHANNEL):
        for point in (node.attributes or {}).get("points", []):
            device = devices.get(_uuid(point.get("device_id")))
            if device is not None:
                counts[device] = counts.get(device, 0) + 1
    return counts


async def node_has_points(db: AsyncSession, job_id: uuid.UUID, node_id: uuid.UUID) -> bool:
    """Whether any channel or output patch point is on the device node."""
    for member in await job_nodes(db, job_id):
        if member.kind in (CHANNEL, OUTPUT) and not member.legacy_ref:
            if any(
                p.get("device_id") == str(node_id)
                for p in (member.attributes or {}).get("points", [])
            ):
                return True
    return False


async def device_has_points(db: AsyncSession, job_id: uuid.UUID, device_id: uuid.UUID) -> bool:
    """Whether the device (by its public id) has patch points, so it cannot be removed."""
    node = await device_node(db, job_id, device_id)
    return node is not None and await node_has_points(db, job_id, node.id)


# --- writes ---------------------------------------------------------------------------------


def _text(data: dict) -> dict:
    return {k: ("" if (k in POINT_TEXT and v is None) else v) for k, v in data.items()}


def _channel_name(attributes: dict) -> str:
    return attributes.get("source_label") or f"Ch {attributes.get('channel_number') or 0}"


def channel_node(job_id: uuid.UUID | None, list_node: GraphDevice, data: dict) -> GraphDevice:
    # A channel inherits the scope (job or venue) of the list it belongs to, so the same
    # helper builds both job and venue channel-list members.
    venue_id = list_node.venue_id
    attributes: dict[str, Any] = {
        "list_id": str(list_node.id),
        "channel_list_id": str(public_id(list_node)),
        "source_label": data.get("source_label") or "",
        "points": [],
        **{key: data[key] for key in CHANNEL_ATTRS if data.get(key) is not None},
    }
    return GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id if venue_id is None else None,
        venue_id=venue_id,
        domain="audio",
        kind=CHANNEL,
        name=_channel_name(attributes),
        position=attributes.get("channel_number") or 0,
        notes=data.get("notes") or "",
        attributes=attributes,
        # A channel is the logical endpoint of a source signal: a mic or a digital stagebox
        # feeds *into* the channel, and the channel then feeds *out* to a bus / PA. So it needs
        # both an `in` (where the source terminates — the true end of the chain) and the existing
        # `out` (toward the mix). Edges terminating on a channel node are valid without force.
        ports=normalize_channel_ports(
            [
                {"id": "in", "direction": "in", "signal": "audio"},
                {"id": "out", "direction": "out", "signal": "audio"},
            ]
        ),
        stockwire_product_id=data.get("stockwire_product_id"),
        stockwire_product_name=data.get("stockwire_product_name"),
    )


def output_node(
    job_id: uuid.UUID | None, list_node: GraphDevice, data: dict, position: int
) -> GraphDevice:
    venue_id = list_node.venue_id
    attributes: dict[str, Any] = {
        "list_id": str(list_node.id),
        "channel_list_id": str(public_id(list_node)),
        "points": [],
        **{key: data[key] for key in OUTPUT_ATTRS if data.get(key) is not None},
    }
    return GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id if venue_id is None else None,
        venue_id=venue_id,
        domain="audio",
        kind=OUTPUT,
        name=data.get("name") or "Output",
        position=data.get("position", position),
        notes=data.get("notes") or "",
        attributes=attributes,
        ports=[
            {"id": "in", "direction": "in", "signal": "audio"},
            {"id": "out", "direction": "out", "signal": "audio", "max_connections": FAN_OUT},
        ],
    )


async def create_list(
    db: AsyncSession,
    job_id: uuid.UUID | None = None,
    data: dict | None = None,
    *,
    venue_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    data = data or {}
    node = GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id,
        venue_id=venue_id,
        domain="audio",
        kind=LIST,
        name=data.get("name") or "Input List",
        position=data.get("position") or 0,
        attributes={k: data[k] for k in LIST_ATTRS if data.get(k) is not None},
        ports=[],
        stockwire_product_id=data.get("mixer_product_id"),
        stockwire_product_name=data.get("mixer_product_name"),
    )
    db.add(node)
    await db.flush()
    return list_row(node, [], {})


async def update_list(
    db: AsyncSession, list_id: uuid.UUID, data: dict, job_id: uuid.UUID | None = None
) -> SimpleNamespace | None:
    node = await find_node(db, LIST, list_id, job_id)
    if node is None:
        return None
    attributes = dict(node.attributes or {})
    for key, value in data.items():
        if value is None and key not in CLEARABLE:
            continue
        if key in LIST_ATTRS:
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
        elif key in ("name", "position"):
            setattr(node, key, value)
    node.attributes = attributes
    node.stockwire_product_id = attributes.get("mixer_product_id")
    node.stockwire_product_name = attributes.get("mixer_product_name")
    await db.flush()
    return await get_list(db, list_id, job_id)


async def delete_children(db: AsyncSession, list_node: GraphDevice) -> tuple[list[str], list[str]]:
    """Delete the channels and outputs of a list (and their edges) before the list itself goes."""
    nodes, edges = await delete_node_tree(db, list_node, keep_root=True)
    return nodes, edges


async def delete_node_tree(
    db: AsyncSession, node: GraphDevice, keep_root: bool = False
) -> tuple[list[str], list[str]]:
    """Delete a node with its edges (and, for a list, its channels and outputs).

    Returns the ids of the nodes and of the edges removed, for the caller to publish.
    """
    nodes = [node]
    if node.kind == LIST:
        nodes += [
            n
            for n in await job_nodes(db, node.job_id)
            if n.kind in (CHANNEL, OUTPUT) and _list_of(n) == str(node.id)
        ]
    ids = {n.id for n in nodes}
    removed_edges = []
    for edge in (
        await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == node.job_id))
    ).all():
        if edge.src_device_id in ids or edge.dst_device_id in ids:
            removed_edges.append(str(edge.id))
            await db.delete(edge)
    if node.kind == LIST:
        # a device's sound list was a foreign key with ON DELETE SET NULL
        await devices_native.clear_attribute(db, node.job_id, "sound_list_id", public_id(node))
    for member in nodes[1:] if keep_root else nodes:
        await db.delete(member)
    await db.flush()
    return [str(n.id) for n in (nodes[1:] if keep_root else nodes)], removed_edges


async def delete_list(db: AsyncSession, list_id: uuid.UUID, job_id: uuid.UUID | None = None):
    node = await find_node(db, LIST, list_id, job_id)
    if node is None:
        return None
    return await delete_node_tree(db, node)


async def create_channel(db: AsyncSession, list_id: uuid.UUID, data: dict) -> SimpleNamespace:
    list_node = await find_node(db, LIST, list_id)
    if list_node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    node = channel_node(list_node.job_id, list_node, data)
    db.add(node)
    await db.flush()
    await plot_native_performer(db, node)
    return channel_row(node, {})


async def plot_native_performer(db: AsyncSession, node: GraphDevice) -> None:
    """A channel made or renamed with a performer: the performer elements follow its name."""
    name = (node.attributes or {}).get("performer_name")
    if name is not None:
        await plot_native.performer_from_channel(db, node.job_id, public_id(node), name)


def apply_channel(node: GraphDevice, data: dict) -> None:
    """Write column-named channel data (what the old update took) onto the node."""
    attributes = dict(node.attributes or {})
    for key, value in data.items():
        if value is None and key not in CLEARABLE:
            continue
        if key == "source_label":
            attributes[key] = value or ""
        elif key == "notes":
            node.notes = value
        elif key in ("stockwire_product_id", "stockwire_product_name"):
            setattr(node, key, value)
        elif key in CHANNEL_ATTRS:
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
    node.attributes = attributes
    node.name = _channel_name(attributes)
    node.position = attributes.get("channel_number") or node.position


async def update_channel(
    db: AsyncSession,
    channel_id: uuid.UUID,
    data: dict,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
) -> SimpleNamespace | None:
    node = await find_node(db, CHANNEL, channel_id, job_id, venue_id)
    if node is None:
        return None
    apply_channel(node, data)
    await db.flush()
    if "performer_name" in data:
        await plot_native_performer(db, node)
    return await get_channel(db, channel_id, node.job_id)


async def delete_channel(
    db: AsyncSession, channel_id: uuid.UUID, job_id: uuid.UUID | None = None
) -> tuple[list[str], list[str]] | None:
    node = await find_node(db, CHANNEL, channel_id, job_id)
    return await delete_node_tree(db, node) if node else None


async def create_output(db: AsyncSession, list_id: uuid.UUID, data: dict) -> SimpleNamespace:
    list_node = await find_node(db, LIST, list_id)
    if list_node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    node = output_node(list_node.job_id, list_node, data, data.get("position") or 0)
    db.add(node)
    await db.flush()
    return output_row(node, {})


async def update_output(
    db: AsyncSession, output_id: uuid.UUID, data: dict, job_id: uuid.UUID | None = None
) -> SimpleNamespace | None:
    node = await find_node(db, OUTPUT, output_id, job_id)
    if node is None:
        return None
    attributes = dict(node.attributes or {})
    for key, value in data.items():
        if value is None and key not in CLEARABLE:
            continue
        if key in ("name", "position"):
            setattr(node, key, value)
        elif key == "notes":
            node.notes = value
        elif key in OUTPUT_ATTRS:
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
    node.attributes = attributes
    await db.flush()
    return await get_output(db, output_id, node.job_id)


async def delete_output(
    db: AsyncSession, output_id: uuid.UUID, job_id: uuid.UUID | None = None
) -> tuple[list[str], list[str]] | None:
    node = await find_node(db, OUTPUT, output_id, job_id)
    return await delete_node_tree(db, node) if node else None


async def _device_node_id(db: AsyncSession, job_id: uuid.UUID, device_id: Any) -> str | None:
    if device_id is None:
        return None
    node = await device_node(db, job_id, device_id)
    if node is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
    return str(node.id)


async def _store_points(db: AsyncSession, node: GraphDevice, points: list[dict]) -> None:
    node.attributes = {**(node.attributes or {}), "points": points}
    await db.flush()


async def create_point(
    db: AsyncSession, kind: str, owner_id: uuid.UUID, data: dict
) -> SimpleNamespace | None:
    node = await find_node(db, kind, owner_id)
    if node is None:
        return None
    data = _text(data)
    point = {
        "point_id": str(uuid.uuid4()),
        "position": data.get("position") or 0,
        "point_type": data.get("point_type") or "mixer",
        "connector": data.get("connector") or "",
        "patch_label": data.get("patch_label") or "",
        "notes": data.get("notes") or "",
        "device_id": await _device_node_id(db, node.job_id, data.get("device_id")),
        "revision": 1,
    }
    if kind == OUTPUT:
        point.update(
            parallel=bool(data.get("parallel")),
            parent_id=str(data["parent_id"]) if data.get("parent_id") else None,
            bus_connector=data.get("bus_connector"),
        )
    await _store_points(db, node, [*(node.attributes or {}).get("points", []), point])
    return await get_point(db, kind, owner_id, uuid.UUID(point["point_id"]))


async def update_point(
    db: AsyncSession, kind: str, owner_id: uuid.UUID, point_id: uuid.UUID, data: dict
) -> SimpleNamespace | None:
    found = await find_point(db, kind, owner_id, point_id)
    if found is None:
        return None
    node, _ = found
    data = _text(data)
    changes: dict[str, Any] = {}
    for key, value in data.items():
        if value is None and key not in CLEARABLE:
            continue
        if key == "device_id":
            changes[key] = await _device_node_id(db, node.job_id, value)
        elif key == "parent_id":
            changes[key] = str(value) if value else None
        elif key in ("position", "point_type", *POINT_KEYS, "parallel", "bus_connector"):
            changes[key] = value
    points = [
        {**p, **changes, "revision": (p.get("revision") or 1) + 1}
        if p["point_id"] == str(point_id)
        else p
        for p in (node.attributes or {}).get("points", [])
    ]
    await _store_points(db, node, points)
    return await get_point(db, kind, owner_id, point_id)


async def delete_point(
    db: AsyncSession, kind: str, owner_id: uuid.UUID, point_id: uuid.UUID
) -> bool:
    found = await find_point(db, kind, owner_id, point_id)
    if found is None:
        return False
    node, gone = found
    # an output point's children are handed to its parent (nothing is left without a source)
    points = [
        {**p, "parent_id": gone.get("parent_id")} if p.get("parent_id") == gone["point_id"] else p
        for p in (node.attributes or {}).get("points", [])
        if p["point_id"] != gone["point_id"]
    ]
    await _store_points(db, node, points)
    return True


async def replace_points(db: AsyncSession, node: GraphDevice, points: list[dict]) -> None:
    await _store_points(db, node, points)


def new_point(
    position: int,
    device_node_id: uuid.UUID,
    point_type: str,
    step: Any = None,
    parent_id: str | None = None,
    *,
    output: bool = False,
) -> dict:
    """A point for a chain replace (the graph's ``PUT .../chain``)."""
    point = {
        "point_id": str(uuid.uuid4()),
        "position": position,
        "point_type": point_type,
        "connector": getattr(step, "connector", "") or "",
        "patch_label": getattr(step, "patch_label", "") or "",
        "notes": getattr(step, "notes", "") or "",
        "device_id": str(device_node_id),
        "revision": 1,
    }
    if output:
        point.update(
            parent_id=parent_id,
            parallel=bool(getattr(step, "parallel", False)),
            bus_connector=getattr(step, "bus_connector", None),
        )
    return point


# --- the graph PATCH of a node -------------------------------------------------------------


async def after_patch(db: AsyncSession, node: GraphDevice, data: dict) -> None:
    """A PATCH of a list, channel or output node: keep its name, number and label in step.

    The PATCH is already on the node. For a channel a new ``name`` is the source label and a
    ``position`` is the channel number (and the reverse: the node keeps one meaning whichever field
    the caller sends); a list or an output keeps ``name`` and ``position`` as they are. Fields the
    old row kept NOT NULL fall back to their default when a client sends null.
    """
    if node.legacy_ref or node.kind not in KINDS:
        return
    attributes = dict(node.attributes or {})
    sent = data.get("attributes") or {}
    if node.kind == CHANNEL:
        if data.get("name") is not None:  # a rename is the new source label, as it always was
            attributes["source_label"] = data["name"]
        if data.get("position") is not None and "channel_number" not in sent:
            attributes["channel_number"] = data["position"]
        for key, default in CHANNEL_DEFAULTS.items():
            if attributes.get(key) is None:
                attributes[key] = default
        if attributes.get("channel_number") is None:
            attributes["channel_number"] = node.position
        node.attributes = attributes
        node.name = _channel_name(attributes)
        node.position = attributes["channel_number"]
        if "performer_name" in sent:
            await plot_native_performer(db, node)
    elif node.kind == OUTPUT:
        if attributes.get("mode") is None:
            attributes["mode"] = "mono"
        node.attributes = attributes
    else:
        if "stockwire_product_id" in data and "mixer_product_id" not in sent:
            attributes["mixer_product_id"] = data["stockwire_product_id"]
        if "stockwire_product_name" in data and "mixer_product_name" not in sent:
            attributes["mixer_product_name"] = data["stockwire_product_name"]
        attributes = {k: v for k, v in attributes.items() if k not in LIST_ATTRS or v is not None}
        node.attributes = attributes
        node.stockwire_product_id = attributes.get("mixer_product_id")
        node.stockwire_product_name = attributes.get("mixer_product_name")
    await db.flush()


# --- edges ----------------------------------------------------------------------------------


def _owner_of_edge(edge: ConnectionEdge) -> uuid.UUID | None:
    return _uuid((edge.attributes or {}).get("chain"))


async def edge_patch(db: AsyncSession, edge: ConnectionEdge, data: dict) -> GraphDevice | None:
    """A PATCH of an edge's connector / label / notes is a change to the point it stands for.

    The edge already carries the new values. Returns the node that owns the point when it
    changed, so the caller syncs (the other edge attributes are derived from the point).
    """
    attrs = (edge.attributes or {}).get("legacy_ref", "")
    table = attrs.partition(":")[0]
    if table not in ("channel_patch_points", "output_patch_points", "channel_list_outputs"):
        return None
    sent = data.get("attributes") or {}
    if table == "channel_list_outputs":  # the console -> bus edge carries the first point
        first = (edge.attributes or {}).get("first_point") or {}
        sent = sent.get("first_point") or {}
        point_id = first.get("point_id")
    else:
        point_id = (edge.attributes or {}).get("point_id")
    changes = {k: sent[k] for k in POINT_KEYS if k in sent}
    owner = _owner_of_edge(edge)
    if not changes or not point_id or owner is None:
        return None
    node = await db.get(GraphDevice, owner)
    if node is None or node.legacy_ref:
        return None
    await update_point(
        db,
        node.kind,
        public_id(node),
        uuid.UUID(point_id),
        {k: v or "" for k, v in changes.items()},
    )
    return node


async def edge_delete(db: AsyncSession, edge: ConnectionEdge) -> GraphDevice | None:
    """Deleting an edge removes the point it stands for."""
    ref = (edge.attributes or {}).get("legacy_ref", "")
    table = ref.partition(":")[0]
    if table not in ("channel_patch_points", "output_patch_points", "channel_list_outputs"):
        return None
    if table == "channel_list_outputs":
        point_id = ((edge.attributes or {}).get("first_point") or {}).get("point_id")
    else:
        point_id = (edge.attributes or {}).get("point_id")
    owner = _owner_of_edge(edge)
    node = await db.get(GraphDevice, owner) if owner else None
    if not point_id or node is None or node.legacy_ref:
        return None
    return node if await delete_point(db, node.kind, public_id(node), uuid.UUID(point_id)) else None


# --- the sync -------------------------------------------------------------------------------


async def sync_edges(builder) -> None:
    """Draw channel input paths and output chains from their native nodes.

    ``builder`` is the running ``Backfill``: the edges go through its ``edge()`` (refs = the point
    ids, as the old rows' ids were), so they are diffed, keep their ids and are pruned when their
    point is gone. Channel patch points run toward the channel endpoint; output chains retain their
    console-outward direction. A point whose device has no node is skipped (as a missing device
    always was).
    """
    nodes = await job_nodes(builder.db, builder.job_id)
    by_id = {n.id: n for n in (*nodes, *builder.devices.values())}
    for node in _of_kind(nodes, CHANNEL):
        number = (node.attributes or {}).get("channel_number")
        points = []
        for point in _sorted(node):
            target = by_id.get(_uuid(point.get("device_id")))
            if target is None or target.legacy_ref is None:
                builder.result.notes.append(f"patch point {point['point_id']}: device missing")
                continue
            points.append((point, target))

        # Older workspaces stored this as an unreferenced mic->channel edge. Replace that edge
        # with the derived relation below when the linked source is still selected.
        source_id = _uuid((node.attributes or {}).get("source_device_id"))
        source = by_id.get(source_id)
        if source is not None and source.id != node.id:
            old_edges = (
                await builder.db.scalars(
                    select(ConnectionEdge).where(
                        ConnectionEdge.job_id == builder.job_id,
                        ConnectionEdge.signal == "audio",
                        ConnectionEdge.src_device_id == source.id,
                        ConnectionEdge.dst_device_id == node.id,
                    )
                )
            ).all()
            for edge in old_edges:
                if not (edge.attributes or {}).get("legacy_ref"):
                    await builder.db.delete(edge)
                    builder.result.removed_edges.append(edge.id)
                    builder.result.removed += 1

            out_port = next(
                (
                    port
                    for port in (source.ports or [])
                    if port.get("direction") == "out"
                    and "xlr" in (port.get("connector") or "").lower()
                    and port.get("signal") in (None, "audio")
                ),
                None,
            )
            if out_port is not None:
                first = points[0] if points else None
                first_connector = first[0].get("connector") if first else ""
                destination = first[1] if first else node
                builder.edge(
                    f"channel_sources:{node.id}",
                    "audio",
                    source,
                    out_port["id"],
                    destination,
                    builder.port(destination, "in", "audio", first_connector or ""),
                    attributes={"channel_id": str(node.id), "channel_source": True},
                )

        for index, (point, source_step) in enumerate(points):
            destination = points[index + 1][1] if index + 1 < len(points) else node
            destination_connector = (
                points[index + 1][0].get("connector")
                if index + 1 < len(points)
                else (node.attributes or {}).get("input_type")
            )
            row = _ns(point)
            builder.edge(
                f"channel_patch_points:{point['point_id']}",
                "audio",
                source_step,
                builder.port(source_step, "out", "audio", destination_connector or ""),
                destination,
                builder.port(destination, "in", "audio", destination_connector or ""),
                attributes={
                    "channel_number": number,
                    "cable_point_id": (
                        str(points[index + 1][0]["point_id"]) if index + 1 < len(points) else None
                    ),
                    **_point_attrs(row, node),
                },
            )
    for bus in _of_kind(nodes, OUTPUT):
        chain = [_ns(p) for p in _sorted(bus) if by_id.get(_uuid(p.get("device_id"))) is not None]
        by_point = {p.id: p for p in chain}
        attributes = bus.attributes or {}
        console = by_id.get(_uuid(chain[0].device)) if chain else None
        if console is not None:
            builder.edge(
                f"channel_list_outputs:{public_id(bus)}",
                "audio",
                console,
                builder.port(console, "out", "audio", attributes.get("connector") or ""),
                bus,
                "in",
                attributes={
                    "connector": attributes.get("connector"),
                    "first_point": _point_attrs(chain[0], bus, bus_connector=True),
                    "chain": str(bus.id),
                    "position": chain[0].position,
                },
            )
        for index, point in enumerate(chain):
            if index == 0:
                continue
            parent = by_point.get(point.parent_id) if point.parent_id else chain[index - 1]
            target = by_id.get(_uuid(point.device))
            if parent is None or target is None:
                continue
            src = bus if parent is chain[0] else by_id.get(_uuid(parent.device))
            if src is None:
                continue
            builder.edge(
                f"output_patch_points:{point.id}",
                "audio",
                src,
                "out" if src is bus else builder.port(src, "out", "audio", point.connector),
                target,
                builder.port(target, "in", "audio", point.connector),
                attributes={
                    "output_id": str(public_id(bus)),
                    "parallel": point.parallel,
                    **_point_attrs(point, bus, bus_connector=True),
                },
            )


def _sorted(node: GraphDevice) -> list[dict]:
    return sorted((node.attributes or {}).get("points", []), key=lambda p: p.get("position") or 0)


def _ns(point: dict) -> SimpleNamespace:
    """A point as ``backfill._point_attrs`` and the edge builder read it."""
    return SimpleNamespace(
        id=_uuid(point["point_id"]),
        position=point.get("position") or 0,
        point_type=point.get("point_type") or "mixer",
        connector=point.get("connector") or "",
        patch_label=point.get("patch_label") or "",
        notes=point.get("notes") or "",
        parent_id=_uuid(point.get("parent_id")),
        parallel=bool(point.get("parallel")),
        bus_connector=point.get("bus_connector"),
        device=point.get("device_id"),
    )


async def plot_targets(db: AsyncSession, job_id: uuid.UUID) -> dict[str, Any]:
    """What a plot element can link to: the public ids of the channels and the patch points
    (with the public id of the device each is on), for ``plot_native`` to resolve and validate."""
    nodes = await job_nodes(db, job_id)
    devices = _device_public(nodes)
    channels: dict[uuid.UUID, GraphDevice] = {}
    inputs: dict[uuid.UUID, uuid.UUID | None] = {}
    outputs: dict[uuid.UUID, uuid.UUID | None] = {}
    for node in _of_kind(nodes, CHANNEL):
        channels[public_id(node)] = node
        for p in (node.attributes or {}).get("points", []):
            inputs[uuid.UUID(p["point_id"])] = devices.get(_uuid(p.get("device_id")))
    for node in _of_kind(nodes, OUTPUT):
        for p in (node.attributes or {}).get("points", []):
            outputs[uuid.UUID(p["point_id"])] = devices.get(_uuid(p.get("device_id")))
    return {
        "channels": channels,
        "patch_point_device": inputs,
        "output_point_device": outputs,
        "now": datetime.now(),
    }


# --- events ---------------------------------------------------------------------------------


async def publish_nodes(db: AsyncSession, job_id: uuid.UUID, node_ids: list[uuid.UUID]) -> None:
    """Tell open workspaces about nodes a legacy-API write created or changed.

    The sync that follows every legacy write publishes only what *it* changed; these nodes were
    written before it, so they are announced here (the edges follow from the sync).
    """
    from app.domains.audio.ws import publish_job_event
    from app.domains.graph import schemas

    for node_id in dict.fromkeys(node_ids):
        node = await db.get(GraphDevice, node_id)
        if node is not None:
            await db.refresh(node)
            payload = schemas.GraphDeviceRead.model_validate(node).model_dump(mode="json")
            await publish_job_event(job_id, "graph.device.upsert", payload)


async def publish_removed(job_id: uuid.UUID, removed: tuple[list[str], list[str]] | None) -> None:
    """Tell open workspaces that nodes (and their edges) were deleted."""
    from app.domains.audio.ws import publish_job_event

    if removed is None:
        return
    nodes, edges = removed
    for index, node_id in enumerate(nodes):
        await publish_job_event(
            job_id, "graph.device.delete", {"id": node_id, "edge_ids": edges if index == 0 else []}
        )


async def node_id_of(db: AsyncSession, kind: str, ident: uuid.UUID) -> uuid.UUID | None:
    node = await find_node(db, kind, ident)
    return node.id if node else None
