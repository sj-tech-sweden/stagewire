"""Stage plot elements on the graph (no legacy table behind them).

A plot element is a ``plot_element`` node (domain ``other``) with no ``legacy_ref``. Its public id
(``ids.public_id``) is its legacy id for an imported element (``attributes.legacy_id``) and its
own node id for a new one; the plot, the cable routes and the load tree key on that id.

Everything the old row held is on the node:

- geometry is the node's canvas (``canvas_x_cm`` / ``canvas_y_cm`` / ``canvas_rotation`` =
  ``position_x`` / ``position_y`` / ``rotation``), the label is ``attributes.label`` and the node
  name follows it (``label`` or, empty, the element type);
- the appearance and specs are attributes under their old column names (``element_type``,
  ``width_cm``, ``height_cm``, ``image_url``, ``coverage_angle_h``, ``coverage_distance_m``,
  ``focal_mm``, ``power_connector``);
- the six links to channel / device / patch point / output point / video input / lens are the
  *public ids* of their targets (``linked_*_id``). They are plain ids, not foreign keys, so a
  target that is deleted leaves a dangling id until the next sync, which clears it
  (``sync_links``, the same effect the foreign keys' ``ON DELETE SET NULL`` had);
- the load links are the graph *node ids* of the rigging point and of the power host
  (``rigging_point_id`` / ``power_node_id``), the way fixtures and devices hold them; the views
  below turn them back into public ids for the power engine and the rigging summary.

The link edges the plot draws (``link`` signal, role = what is linked) are derived from those
attributes by ``sync_links``, called from the sync; a link set through the graph (a link edge, or
``PUT plot-elements/{id}/links``) writes the attribute and the sync draws the edge.
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph import power_native
from app.domains.graph.ids import public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice

ELEMENT_FIELDS = (
    "element_type",
    "width_cm",
    "height_cm",
    "image_url",
    "coverage_angle_h",
    "coverage_distance_m",
    "focal_mm",
    "power_connector",
)
# attribute (= old column) -> role of the ``link`` edge from the element to its target
LINKS = {
    "linked_channel_id": "channel",
    "linked_device_id": "device",
    "linked_patch_point_id": "patch_point",
    "linked_output_point_id": "output_point",
    "linked_video_input_id": "video_input",
    "linked_lens_device_id": "lens",
}
ROLE_COLUMN = {role: column for column, role in LINKS.items()}
# Values the old row's NOT NULL columns defaulted to; a null in an edit keeps the default.
DEFAULTS = {
    "element_type": "custom",
    "width_cm": 60.0,
    "height_cm": 60.0,
    "image_url": "",
    "coverage_angle_h": 0.0,
    "coverage_distance_m": 0.0,
    "power_connector": "",
}
CANVAS = {"position_x": "canvas_x_cm", "position_y": "canvas_y_cm", "rotation": "canvas_rotation"}
# the order the source link of an element is chosen in (what its cable starts at)
SOURCE_ORDER = ("channel", "video_input", "output_point", "patch_point")


def is_element(node: GraphDevice | None) -> bool:
    return node is not None and node.kind == "plot_element"


def _age(node: GraphDevice) -> tuple[float, str]:
    """Oldest first; ``timestamp`` so a naive and an aware datetime (sqlite, postgres) compare."""
    return (node.created_at.timestamp() if node.created_at else 0.0, str(node.id))


async def element_nodes(db: AsyncSession, job_id: uuid.UUID) -> list[GraphDevice]:
    rows = await db.scalars(
        select(GraphDevice).where(GraphDevice.job_id == job_id, GraphDevice.kind == "plot_element")
    )
    return sorted(rows.all(), key=_age)


async def host_of(db: AsyncSession, job_id: uuid.UUID, element_id: uuid.UUID) -> GraphDevice | None:
    return next((n for n in await element_nodes(db, job_id) if public_id(n) == element_id), None)


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


async def _id_maps(db: AsyncSession, job_id: uuid.UUID) -> tuple[dict, dict]:
    """Graph node id (as the attributes hold it) -> public id, for rigging points and power."""
    points = {
        str(n.id): public_id(n)
        for n in (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.kind == "rigging_point"
                )
            )
        ).all()
    }
    power = {str(h.id): pid for pid, h in (await power_native.host_nodes(db, job_id)).items()}
    return points, power


def view(node: GraphDevice, points: dict, power: dict, link_edges: dict) -> SimpleNamespace:
    """An element shaped like the old ``StagePlotElement`` row.

    ``graph_device_id`` and the source pair are derived from the element's link edges (the node of
    its device, and the first of channel / video input / output point / patch point linked).
    """
    a = node.attributes or {}
    targets = link_edges.get(node.id, {})
    source_role = next((r for r in SOURCE_ORDER if r in targets), None)
    return SimpleNamespace(
        id=public_id(node),
        node_id=node.id,
        job_id=node.job_id,
        label=a.get("label") or "",
        position_x=node.canvas_x_cm or 0.0,
        position_y=node.canvas_y_cm or 0.0,
        rotation=node.canvas_rotation or 0.0,
        **{key: a.get(key, DEFAULTS.get(key)) for key in ELEMENT_FIELDS},
        **{column: _uuid(a.get(column)) for column in LINKS},
        rigging_point_id=points.get(a.get("rigging_point_id")),
        power_node_id=power.get(a.get("power_node_id")),
        graph_device_id=targets.get("device"),
        graph_link_role=None,
        graph_source_id=targets.get(source_role) if source_role else None,
        graph_source_role=source_role,
    )


async def load_elements(db: AsyncSession, job_id: uuid.UUID) -> list[SimpleNamespace]:
    nodes = await element_nodes(db, job_id)
    if not nodes:
        return []
    points, power = await _id_maps(db, job_id)
    ids = {n.id for n in nodes}
    link_edges: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
    for edge in (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == job_id, ConnectionEdge.signal == "link"
            )
        )
    ).all():
        if edge.src_device_id in ids:
            link_edges.setdefault(edge.src_device_id, {})[edge.dst_port] = edge.dst_device_id
    return [view(n, points, power, link_edges) for n in nodes]


async def get_element(
    db: AsyncSession, job_id: uuid.UUID, element_id: uuid.UUID
) -> SimpleNamespace | None:
    return next((e for e in await load_elements(db, job_id) if e.id == element_id), None)


async def _graph_ids(db: AsyncSession, job_id: uuid.UUID, data: dict) -> dict:
    """The point and power node a caller names by public id, as graph node ids (or None)."""
    out: dict = {}
    if "rigging_point_id" in data:
        wanted = data["rigging_point_id"]
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
                if public_id(n) == wanted
            ),
            None,
        )
        out["rigging_point_id"] = str(node.id) if node and wanted else None
    if "power_node_id" in data:
        host = (
            await power_native.host_of(db, job_id, data["power_node_id"])
            if data["power_node_id"]
            else None
        )
        out["power_node_id"] = str(host.id) if host else None
    return out


def _name(attributes: dict) -> str:
    return attributes.get("label") or attributes.get("element_type") or "element"


def _apply(node: GraphDevice, data: dict, graph_ids: dict) -> None:
    """Write column-named ``data`` (what the old update took) onto the node."""
    attributes = dict(node.attributes or {})
    for key in ELEMENT_FIELDS:
        if key in data:
            value = data[key]
            if value is None and key in DEFAULTS:
                value = DEFAULTS[key]
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
    if "label" in data:
        attributes["label"] = data["label"] or ""
    for column in LINKS:
        if column in data:
            if data[column] is None:
                attributes.pop(column, None)
            else:
                attributes[column] = str(data[column])
    for key, value in graph_ids.items():
        if value is None:
            attributes.pop(key, None)
        else:
            attributes[key] = value
    if not attributes.get("power_node_id"):
        attributes["power_connector"] = ""
    for column, canvas in CANVAS.items():
        if data.get(column) is not None:
            setattr(node, canvas, data[column])
    node.attributes = attributes
    node.name = _name(attributes)


def normalize_new(fields: dict) -> dict:
    """The fields of a ``plot_element`` node made through the graph API, with the element
    defaults the old row gave (type, size, empty label) and the label the plot always derived
    from the name."""
    attributes = dict(fields.get("attributes") or {})
    attributes["label"] = attributes["label"] if "label" in attributes else fields.get("name") or ""
    for key, default in DEFAULTS.items():
        if attributes.get(key) is None:
            attributes[key] = default
    return {
        **fields,
        "attributes": attributes,
        "name": _name(attributes),
        "canvas_x_cm": fields.get("canvas_x_cm") or 0.0,
        "canvas_y_cm": fields.get("canvas_y_cm") or 0.0,
        "canvas_rotation": fields.get("canvas_rotation") or 0.0,
    }


async def create_element(db: AsyncSession, job_id: uuid.UUID, data: dict) -> SimpleNamespace:
    """Make an element from column-named data (the body of ``POST plot-elements``)."""
    node = GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id,
        domain="other",
        kind="plot_element",
        name="element",
        position=0,
        attributes={**DEFAULTS, "label": ""},
        ports=[],
        canvas_x_cm=0.0,
        canvas_y_cm=0.0,
        canvas_rotation=0.0,
    )
    _apply(node, data, await _graph_ids(db, job_id, data))
    db.add(node)
    await db.flush()
    await performer_to_channel(db, job_id, node)
    points, power = await _id_maps(db, job_id)
    return view(node, points, power, {})


async def update_element(
    db: AsyncSession, job_id: uuid.UUID, element_id: uuid.UUID, data: dict
) -> SimpleNamespace | None:
    node = await host_of(db, job_id, element_id)
    if node is None:
        return None
    _apply(node, data, await _graph_ids(db, job_id, data))
    await db.flush()
    await performer_to_channel(db, job_id, node)
    return await get_element(db, job_id, element_id)


async def delete_element(
    db: AsyncSession, job_id: uuid.UUID, element_id: uuid.UUID
) -> tuple[uuid.UUID, list[uuid.UUID]] | None:
    """Delete an element and its edges; returns its node id and the edge ids (None: no such)."""
    node = await host_of(db, job_id, element_id)
    if node is None:
        return None
    edge_ids = []
    for edge in (
        await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))
    ).all():
        if node.id in (edge.src_device_id, edge.dst_device_id):
            edge_ids.append(edge.id)
            await db.delete(edge)
    await db.delete(node)
    await db.flush()
    return node.id, edge_ids


async def publish_upsert(db: AsyncSession, job_id: uuid.UUID, node_id: uuid.UUID) -> None:
    """Tell open workspaces about a node a plot-element write created or changed."""
    from app.domains.audio.ws import publish_job_event
    from app.domains.graph import schemas

    node = await db.get(GraphDevice, node_id)
    if node is not None:
        await db.refresh(node)
        payload = schemas.GraphDeviceRead.model_validate(node).model_dump(mode="json")
        await publish_job_event(job_id, "graph.device.upsert", payload)


async def publish_delete(job_id: uuid.UUID, node_id: uuid.UUID, edge_ids: list) -> None:
    from app.domains.audio.ws import publish_job_event

    await publish_job_event(
        job_id,
        "graph.device.delete",
        {"id": str(node_id), "edge_ids": [str(e) for e in edge_ids]},
    )


async def clear_links(db: AsyncSession, job_id: uuid.UUID, column: str, value: uuid.UUID) -> None:
    """Clear ``column`` on every element of the job that holds ``value`` (a target went away)."""
    for node in await element_nodes(db, job_id):
        if (node.attributes or {}).get(column) == str(value):
            node.attributes = {k: v for k, v in node.attributes.items() if k != column}


async def performer_to_channel(db: AsyncSession, job_id: uuid.UUID, node: GraphDevice) -> None:
    """A performer element's label is the performer name of the channel it is linked to."""
    a = node.attributes or {}
    channel_id = _uuid(a.get("linked_channel_id"))
    if a.get("element_type") != "performer" or channel_id is None:
        return
    from app.domains.graph import audio_native

    channel = await audio_native.find_node(db, audio_native.CHANNEL, channel_id, job_id)
    if channel is not None:
        channel.attributes = {**channel.attributes, "performer_name": a.get("label") or ""}


async def performer_from_channel(
    db: AsyncSession, job_id: uuid.UUID, channel_id: uuid.UUID, name: str
) -> None:
    """The reverse: a channel's performer name becomes the label of its performer elements."""
    for node in await element_nodes(db, job_id):
        a = node.attributes or {}
        if a.get("element_type") == "performer" and a.get("linked_channel_id") == str(channel_id):
            node.attributes = {**a, "label": name}
            node.name = _name(node.attributes)


async def after_patch(db: AsyncSession, job_id: uuid.UUID, node: GraphDevice, data: dict) -> None:
    """A PATCH of a ``plot_element`` node: keep the label and the node name in step.

    The PATCH is already on the node. A new ``name`` is the new label (as the plot always
    treated a rename); a ``label`` attribute without a name is the label; either way the node name
    is the label, or the element type when it is empty. Attributes the old row kept NOT NULL fall
    back to their default when a client sends null.
    """
    if not is_element(node):
        return
    attributes = dict(node.attributes or {})
    sent = data.get("attributes") or {}
    if data.get("name") is not None:
        attributes["label"] = data["name"]
    elif "label" in sent:
        attributes["label"] = sent["label"] or ""
    for key, default in DEFAULTS.items():
        if attributes.get(key) is None:
            attributes[key] = default
    node.attributes = attributes
    node.name = _name(attributes)
    for column in CANVAS.values():
        if getattr(node, column) is None:
            setattr(node, column, 0.0)
    await db.flush()
    await performer_to_channel(db, job_id, node)


# --- the sync -------------------------------------------------------------------------------


async def _existing_devices(db: AsyncSession, job_id: uuid.UUID) -> set[str]:
    """The ids of the job's devices, to tell a dangling device link."""
    from app.domains.graph import devices_native

    return {str(public_id(n)) for n in await devices_native.device_nodes(db, job_id)}


async def sync_links(builder) -> None:
    """Draw each element's link edges from its attributes and clear links whose target is gone.

    ``builder`` is the running ``Backfill``: the edges go through its ``edge()`` so they are
    diffed, kept stable (same legacy_ref, same edge id) and pruned like every mirrored edge.
    """
    nodes = await element_nodes(builder.db, builder.job_id)
    if not nodes:
        return
    from app.domains.graph import audio_native

    devices = await _existing_devices(builder.db, builder.job_id)
    targets = await audio_native.plot_targets(builder.db, builder.job_id)
    power_hosts = {str(h.id): (pid, h) for pid, h in builder.power_nodes.items()}
    point_nodes = {str(n.id) for n in builder.rigging_points.values()}

    for node in nodes:
        attributes = dict(node.attributes or {})
        pid = public_id(node)
        for column, role in LINKS.items():
            raw = attributes.get(column)
            if not raw:
                continue
            value = _uuid(raw)
            if role == "video_input":
                target = builder.video_inputs.get(value)
                gone = target is None
            elif role == "channel":
                target = targets["channels"].get(value)
                gone = target is None
            elif role in ("patch_point", "output_point"):
                owners = targets[f"{role}_device"]
                gone = value not in owners
                target = None if gone else builder.devices.get(f"device:{owners[value]}")
            else:  # device, lens
                gone = str(value) not in devices
                target = None if gone else builder.devices.get(f"device:{value}")
            if gone:  # what it pointed at was deleted: the link goes with it
                attributes.pop(column)
                continue
            if target is None:
                continue
            builder.edge(
                f"stage_plot_elements.link:{pid}:{role}",
                "link",
                node,
                "link",
                target,
                role,
                attributes={"role": role, "legacy_target": str(value)},
            )
        feeder = attributes.get("power_node_id")
        if feeder:
            hit = power_hosts.get(feeder)
            if hit is None:
                attributes.pop("power_node_id")
                attributes["power_connector"] = ""
            else:
                builder.edge(
                    f"stage_plot_elements.link:{pid}:power_node",
                    "link",
                    node,
                    "link",
                    hit[1],
                    "power_node",
                    attributes={"role": "power_node", "legacy_target": str(hit[0])},
                )
        if attributes.get("rigging_point_id") and attributes["rigging_point_id"] not in point_nodes:
            attributes.pop("rigging_point_id")
        if attributes != (node.attributes or {}):
            node.attributes = attributes
