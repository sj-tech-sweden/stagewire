"""Gear (stageboxes, mixers, cameras, speakers, fixtures' devices, ...) on the graph.

A device is a graph node whose ``legacy_ref`` is ``device:<id>``. The ref is no longer a
link to a table (there is none): it is the device's identity, the marker every module tests
(``is_device``), the id plot links, patch points, loads and cable routes hold (``ids.public_id``
is that id), and what the web app finds a device node by. A device made in the graph has its own
node id in the ref; an imported one keeps its old row id, and its node id.

What the old row held:

- node columns: ``name`` (``device_type`` or "Device" when empty), ``notes``, ``position``,
  ``kind`` (= the device type), ``domain`` (``lighting`` with a fixture type, ``video`` with video
  specs, else ``audio``), ``stockwire_product_id`` / ``stockwire_product_name``, ``ports``;
- attributes, only the ones that are set: ``device_type``, ``weight_kg``, ``power_w``,
  ``input_override``, ``output_override``, ``fixture_type``, ``channel_mode``,
  ``footprint_channels``, ``default_gel``, ``power_inlet`` and the video specs under the column
  names; ``sound_list_id`` / ``video_list_id`` (public ids of the list nodes); the load links
  ``power_node_id`` / ``rigging_point_id`` (graph *node ids* of the power host and the point, as
  fixtures and plot elements hold them) and ``power_connector``; ``port_groups`` = the connector
  groups the API shows as ``ports`` (``direction``, ``connector``, ``count``).

``node.ports`` are the ports the graph draws: the groups' ports plus whatever the sync and the
power tree added; a write of the groups regenerates the first and keeps the rest. Nothing resets
them any more.

``device_row`` shapes a node like the old ``AudioDevice`` row, so the audio service and router, the
lighting and rigging services and the reports are unchanged.
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph import power_native
from app.domains.graph.ids import public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice, scope_filter

REF = "device:"
NON_GEAR_KINDS = frozenset(
    {
        "channel",
        "channel_list",
        "output",
        "video_list",
        "video_input",
        "video_destination",
        "rigging_point",
        "dmx_universe",
        "plot_element",
    }
)
SPEC_FIELDS = (
    "sensor_width_mm",
    "focal_min_mm",
    "focal_max_mm",
    "max_distance_m",
    "throw_ratio_min",
    "throw_ratio_max",
    "image_aspect_ratio",
)
# column name -> attribute of the node (graph key)
COLUMN_ATTR = {
    "power_watts": "power_w",
    "weight_kg": "weight_kg",
    "input_override": "input_override",
    "output_override": "output_override",
    "fixture_type": "fixture_type",
    "channel_mode": "channel_mode",
    "footprint_channels": "footprint_channels",
    "default_gel": "default_gel",
    "power_inlet": "power_inlet",
    **{key: key for key in SPEC_FIELDS},
}
# a null in an edit clears only these (elsewhere a null means "not sent", as the row's did)
CLEARABLE = {
    "weight_kg",
    "power_watts",
    "fixture_type",
    "channel_mode",
    "footprint_channels",
    "default_gel",
    "sensor_width_mm",
    "focal_min_mm",
    "focal_max_mm",
    "max_distance_m",
    "throw_ratio_min",
    "throw_ratio_max",
    "image_aspect_ratio",
    "sound_list_id",
    "video_list_id",
    "stockwire_product_id",
    "stockwire_product_name",
    "input_override",
    "output_override",
}


def is_device(node: GraphDevice | None) -> bool:
    return node is not None and bool(node.legacy_ref and node.legacy_ref.startswith(REF))


def is_physical_gear(node: GraphDevice) -> bool:
    """Whether a graph node represents gear that can carry a Stockwire asset link."""
    return node.kind not in NON_GEAR_KINDS and not (
        node.domain == "power" and node.kind in power_native.POWER_KINDS
    )


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _age(node: GraphDevice) -> tuple[float, str]:
    return (node.created_at.timestamp() if node.created_at else 0.0, str(node.id))


def domain_of(attributes: dict) -> str:
    if attributes.get("fixture_id") or attributes.get("fixture_type"):
        return "lighting"
    if (
        attributes.get("video_list_id")
        or attributes.get("throw_ratio_min")
        or attributes.get("sensor_width_mm")
    ):
        return "video"
    return "audio"


def group_ports(groups: list[dict], signal: str) -> list[dict]:
    """The graph ports of a device's connector groups (ids ``in-xlr3``, ``out-x``, ...)."""
    ports: list[dict] = []
    seen: set[str] = set()
    for group in groups or []:
        direction = group.get("direction") or "in"
        connector = (group.get("connector") or "").lower()
        base = f"{direction}-{connector or 'x'}"
        pid, n = base, 1
        while pid in seen:
            n += 1
            pid = f"{base}-{n}"
        seen.add(pid)
        ports.append(
            {
                "id": pid,
                "direction": direction,
                "signal": signal,
                "connector": connector or None,
                "channels": group.get("count") or None,
                "label": "",
            }
        )
    return ports


def _is_group_port(port: dict) -> bool:
    """A connector group is a port with a connector or a channel count (not a power port); the
    generic ports the graph adds on its own carry neither and are not data."""
    return port.get("signal") != "power" and bool(port.get("connector") or port.get("channels"))


def groups_of(ports: list[dict]) -> list[dict]:
    return [
        {
            "direction": p.get("direction") or "in",
            "connector": p.get("connector") or "",
            "count": p.get("channels") or 0,
        }
        for p in ports or []
        if _is_group_port(p)
    ]


def _signal(domain: str) -> str:
    return {"lighting": "dmx", "video": "video"}.get(domain, "audio")


def rebuild_ports(node: GraphDevice, groups: list[dict]) -> None:
    """Ports = the groups' ports + the ports that are not groups (power, generic)."""
    extras = [p for p in node.ports or [] if not _is_group_port(p)]
    node.ports = [*group_ports(groups, _signal(node.domain)), *extras]


def _name(name: str | None, device_type: str | None) -> str:
    return name or device_type or "Device"


# --- reads ----------------------------------------------------------------------------------


async def device_nodes(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> list[GraphDevice]:
    rows = await db.scalars(
        select(GraphDevice).where(
            scope_filter(GraphDevice, job_id, venue_id), GraphDevice.legacy_ref.like(f"{REF}%")
        )
    )
    return sorted(rows.all(), key=lambda n: (n.position, *_age(n)))


async def _id_maps(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> tuple[dict, dict]:
    """Graph node id (as the attributes hold it) -> public id, for rigging points and power."""
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


def device_row(node: GraphDevice, points: dict, power: dict) -> SimpleNamespace:
    """A device shaped like the old ``AudioDevice`` row."""
    a = node.attributes or {}
    return SimpleNamespace(
        id=public_id(node),
        node_id=node.id,
        job_id=node.job_id,
        venue_id=node.venue_id,
        name=node.name,
        device_type=a.get("device_type") or node.kind or "other",
        position=node.position,
        notes=node.notes or "",
        ports=a.get("port_groups") or [],
        stockwire_product_id=node.stockwire_product_id,
        stockwire_product_name=node.stockwire_product_name,
        sound_list_id=_uuid(a.get("sound_list_id")),
        video_list_id=_uuid(a.get("video_list_id")),
        power_inlet=a.get("power_inlet") or "",
        power_node_id=power.get(a.get("power_node_id")),
        power_connector=a.get("power_connector") or "",
        rigging_point_id=points.get(a.get("rigging_point_id")),
        created_at=node.created_at,
        **{column: a.get(attr) for column, attr in COLUMN_ATTR.items() if column != "power_inlet"},
    )


async def load_devices(
    db: AsyncSession, job_id: uuid.UUID | None = None, venue_id: uuid.UUID | None = None
) -> list[SimpleNamespace]:
    nodes = await device_nodes(db, job_id, venue_id)
    if not nodes:
        return []
    points, power = await _id_maps(db, job_id, venue_id)
    return [device_row(n, points, power) for n in nodes]


async def node_of(
    db: AsyncSession,
    device_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
) -> GraphDevice | None:
    query = select(GraphDevice).where(GraphDevice.legacy_ref == f"{REF}{device_id}")
    if job_id is not None:
        query = query.where(GraphDevice.job_id == job_id)
    if venue_id is not None:
        query = query.where(GraphDevice.venue_id == venue_id)
    return (await db.scalars(query)).first()


async def get_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
) -> SimpleNamespace | None:
    node = await node_of(db, device_id, job_id, venue_id)
    if node is None:
        return None
    points, power = await _id_maps(db, node.job_id, node.venue_id)
    return device_row(node, points, power)


async def find_with(
    db: AsyncSession, job_id: uuid.UUID, key: str, value: uuid.UUID
) -> SimpleNamespace | None:
    """The first device whose list link ``key`` (a sound or video list id) is ``value``."""
    for node in await device_nodes(db, job_id):
        if (node.attributes or {}).get(key) == str(value):
            return await get_device(db, public_id(node), job_id)
    return None


# --- writes ---------------------------------------------------------------------------------


async def _graph_ids(
    db: AsyncSession,
    job_id: uuid.UUID | None,
    data: dict,
    venue_id: uuid.UUID | None = None,
) -> dict:
    """The rigging point and power node a caller names by public id, as graph node ids."""
    out: dict = {}
    if data.get("rigging_point_id") is not None or "rigging_point_id" in data:
        wanted = data["rigging_point_id"]
        node = next(
            (
                n
                for n in (
                    await db.scalars(
                        select(GraphDevice).where(
                            scope_filter(GraphDevice, job_id, venue_id),
                            GraphDevice.kind == "rigging_point",
                        )
                    )
                ).all()
                if wanted and public_id(n) == wanted
            ),
            None,
        )
        out["rigging_point_id"] = str(node.id) if node else None
    if "power_node_id" in data:
        wanted = data["power_node_id"]
        host = await power_native.host_of(db, job_id, wanted, venue_id) if wanted else None
        out["power_node_id"] = str(host.id) if host else None
    return out


async def apply(db: AsyncSession, node: GraphDevice, data: dict) -> None:
    """Write column-named data (what the old create and update took) onto the node."""
    attributes = dict(node.attributes or {})
    graph_ids = await _graph_ids(db, node.job_id, data, node.venue_id)
    groups = None
    for key, value in data.items():
        if value is None and key not in CLEARABLE:
            continue
        if key == "name":
            node.name = value
        elif key == "notes":
            node.notes = value
        elif key == "position":
            node.position = value
        elif key == "device_type":
            attributes["device_type"] = value
            node.kind = value
        elif key in ("stockwire_product_id", "stockwire_product_name"):
            setattr(node, key, value)
        elif key == "ports":
            groups = [dict(g) for g in (value or [])]
            attributes["port_groups"] = groups
        elif key in ("sound_list_id", "video_list_id"):
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = str(value)
        elif key == "power_connector":
            attributes[key] = value or ""
        elif key in COLUMN_ATTR:
            attr = COLUMN_ATTR[key]
            if value in (None, ""):
                attributes.pop(attr, None)
            else:
                attributes[attr] = value
    for key, value in graph_ids.items():
        if value is None:
            attributes.pop(key, None)
        else:
            attributes[key] = value
    if not attributes.get("power_node_id"):
        attributes.pop("power_connector", None)
    node.attributes = attributes
    node.domain = domain_of(attributes)
    if not node.name:  # an empty name reads as the device type
        node.name = _name("", attributes.get("device_type"))
    if groups is not None:
        rebuild_ports(node, groups)


async def create_device(
    db: AsyncSession,
    job_id: uuid.UUID | None,
    data: dict,
    venue_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    device_id = uuid.uuid4()
    node = GraphDevice(
        id=device_id,
        job_id=job_id,
        venue_id=venue_id,
        domain="audio",
        kind=data.get("device_type") or "other",
        name="",
        legacy_ref=f"{REF}{device_id}",
        position=0,
        attributes={"device_type": data.get("device_type") or "other"},
        ports=[],
    )
    db.add(node)
    await apply(db, node, {k: v for k, v in data.items() if v is not None or k in CLEARABLE})
    node.ports = group_ports(node.attributes.get("port_groups", []), _signal(node.domain))
    await db.flush()
    points, power = await _id_maps(db, job_id, venue_id)
    return device_row(node, points, power)


async def update_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    data: dict,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
) -> SimpleNamespace | None:
    node = await node_of(db, device_id, job_id, venue_id)
    if node is None:
        return None
    await apply(db, node, data)
    await db.flush()
    points, power = await _id_maps(db, node.job_id, node.venue_id)
    return device_row(node, points, power)


async def delete_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
) -> tuple[list[str], list[str]] | None:
    """Delete the node with its edges; returns the node and edge ids for the caller to publish."""
    node = await node_of(db, device_id, job_id, venue_id)
    if node is None:
        return None
    edges = []
    for edge in (
        await db.scalars(
            select(ConnectionEdge).where(scope_filter(ConnectionEdge, node.job_id, node.venue_id))
        )
    ).all():
        if node.id in (edge.src_device_id, edge.dst_device_id):
            edges.append(str(edge.id))
            await db.delete(edge)
    await db.delete(node)
    await db.flush()
    return [str(node.id)], edges


async def clear_attribute(db: AsyncSession, job_id: uuid.UUID, key: str, value: uuid.UUID) -> None:
    """Clear ``key`` (a list link) on every device that holds ``value`` (the list went away)."""
    for node in await device_nodes(db, job_id):
        if (node.attributes or {}).get(key) == str(value):
            node.attributes = {k: v for k, v in node.attributes.items() if k != key}
            node.domain = domain_of(node.attributes)


def promote(node: GraphDevice, known_types: set[str]) -> None:
    """Make a plain graph node (a catalog item) a device: it takes its own id as its device id."""
    attributes = dict(node.attributes or {})
    kind = node.kind if node.kind in known_types else "other"
    attributes["device_type"] = kind
    attributes["port_groups"] = groups_of(node.ports)
    node.attributes = attributes
    node.legacy_ref = f"{REF}{node.id}"
    node.domain = domain_of(attributes)


async def after_patch(node: GraphDevice, data: dict) -> None:
    """A graph PATCH of a device node (already on the node): keep the groups, type and domain.

    The connector groups are what the node's own ports say; a ``kind`` is the device type; the
    name falls back to the type; the domain follows the specs (a fixture host stays lighting).
    """
    if not is_device(node):
        return
    attributes = dict(node.attributes or {})
    if data.get("kind"):
        attributes["device_type"] = data["kind"]
    elif (data.get("attributes") or {}).get("device_type"):
        node.kind = attributes["device_type"]
    for key in list(attributes):
        if key in COLUMN_ATTR.values() and attributes[key] in (None, ""):
            attributes.pop(key)
    if "ports" in data and data["ports"] is not None:
        attributes["port_groups"] = groups_of(node.ports)
    node.attributes = attributes
    node.domain = domain_of(attributes)
    if not node.name:
        node.name = _name("", attributes.get("device_type"))
