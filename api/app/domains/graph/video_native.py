"""Video lists, inputs and outputs authored directly on the graph (no legacy tables behind them).

Data model. A ``video_input`` or ``video_destination`` node keeps its patch points as the
canonical data, in ``attributes.points`` (each: ``point_id``, ``position``, ``device_id`` = the
device *node* id, ``connector``, ``patch_label``, ``notes``, ``source_port``, ``input_port`` and,
for an output, ``parent_id``). The edges the web app and the graph tools read (``attributes.chain``
= the node, ``point_id``, ...) and an output's ``attributes.roots`` are rebuilt from the points by
``rebuild`` whenever they change, so replacing a chain, deleting a connection and filling a list
from its switcher are all "change the points, rebuild". ``video_readers`` reads the points.

Ids. A point's id is the legacy point id for rows that came from the tables and a new uuid for
new ones; nodes are referred to by their public id (``ids.public_id``).
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import AudioDevice, StagePlotElement
from app.domains.graph.backfill import LEGACY_VIDEO_REFS, Backfill
from app.domains.graph.ids import public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice

VIDEO_KINDS = ("video_list", "video_input", "video_destination")
POINT_KEYS = ("connector", "patch_label", "notes", "source_port", "input_port")


def new_point(
    position: int, device_id: uuid.UUID, step: Any = None, parent_id: str | None = None
) -> dict:
    return {
        "point_id": str(uuid.uuid4()),
        "position": position,
        "device_id": str(device_id),
        "parent_id": parent_id,
        **{key: getattr(step, key, "") or "" for key in POINT_KEYS},
    }


def _edge_attrs(point: dict) -> dict:
    return {
        "point_id": point["point_id"],
        "position": point.get("position") or 0,
        "parent_id": point.get("parent_id"),
        **{key: point.get(key) or "" for key in POINT_KEYS},
    }


async def rebuild(db: AsyncSession, node: GraphDevice, points: list[dict]) -> None:
    """Store the points on the node and rebuild its chain edges (and an output's roots)."""
    points = sorted(points, key=lambda p: p.get("position") or 0)
    old = (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == node.job_id, ConnectionEdge.signal == "video"
            )
        )
    ).all()
    for edge in old:
        if (edge.attributes or {}).get("chain") == str(node.id):
            await db.delete(edge)
    await db.flush()

    wanted = {uuid.UUID(p["device_id"]) for p in points}
    devices = {
        d.id: d
        for d in (
            await db.scalars(select(GraphDevice).where(GraphDevice.id.in_(wanted or {node.id})))
        ).all()
        if d.job_id == node.job_id
    }
    attributes = dict(node.attributes or {})
    attributes["points"] = points
    new_edges: list[ConnectionEdge] = []

    def edge(src, sport, dst, dport, attrs) -> None:
        new_edges.append(
            ConnectionEdge(
                id=uuid.uuid4(),
                job_id=node.job_id,
                signal="video",
                src_device_id=src.id,
                src_port=sport,
                dst_device_id=dst.id,
                dst_port=dport,
                channels=1,
                attributes={"chain": str(node.id), **attrs},
            )
        )

    if node.kind == "video_input":
        prev = node
        for point in points:
            target = devices.get(uuid.UUID(point["device_id"]))
            if target is None or target is prev:
                continue
            edge(
                prev,
                "out"
                if prev is node
                else Backfill.named_port(
                    prev, "out", "video", point["source_port"], point["connector"]
                ),
                target,
                Backfill.named_port(target, "in", "video", point["input_port"], point["connector"]),
                {"input_number": attributes.get("input_number"), **_edge_attrs(point)},
            )
            prev = target
    else:
        ids = {p["point_id"] for p in points if devices.get(uuid.UUID(p["device_id"]))}
        live = [p for p in points if p["point_id"] in ids]
        leaves = {p["point_id"] for p in live} - {p["parent_id"] for p in live if p["parent_id"]}
        by_id = {p["point_id"]: p for p in live}
        for point in live:
            target = devices[uuid.UUID(point["device_id"])]
            parent = by_id.get(point["parent_id"]) if point["parent_id"] else None
            if parent is not None and parent["device_id"] != point["device_id"]:
                src = devices[uuid.UUID(parent["device_id"])]
                edge(
                    src,
                    Backfill.named_port(
                        src, "out", "video", point["source_port"], point["connector"]
                    ),
                    target,
                    Backfill.named_port(
                        target, "in", "video", point["input_port"], point["connector"]
                    ),
                    {"output_id": str(public_id(node)), **_edge_attrs(point)},
                )
            if point["point_id"] in leaves:
                edge(
                    target,
                    Backfill.port(target, "out", "video", point["connector"]),
                    node,
                    "in",
                    {"output_id": str(public_id(node))},
                )
        attributes["roots"] = [
            {"device_id": point["device_id"], **_edge_attrs(point)}
            for point in live
            if point["parent_id"] is None
        ]
        node.ports = [
            {**port, "channels": max(1, len(leaves))} if port.get("id") == "in" else port
            for port in node.ports
        ]
    node.attributes = attributes
    db.add_all(new_edges)
    await db.flush()


def translate_patch(node: GraphDevice, data: dict) -> dict:
    """What a PATCH of a video node means for its own fields (the mirror's old name rules).

    A name edit is the source label of an input and the destination label of an output, and a
    position is its number, so the node keeps one meaning whichever field the caller sends.
    """
    if node.kind not in ("video_input", "video_destination"):
        return data
    attrs = dict(data.get("attributes") or {})
    label, number = (
        ("source_label", "input_number")
        if node.kind == "video_input"
        else ("destination_label", "output_number")
    )
    if data.get("name") is not None and label not in attrs:
        attrs[label] = data["name"]
    if data.get("position") is not None and number not in attrs:
        attrs[number] = max(1, data["position"])
    if attrs.get(number) is not None and data.get("position") is None:
        data = {**data, "position": attrs[number]}
    return {**data, "attributes": attrs} if attrs else data


async def point_from_edge(db: AsyncSession, edge: ConnectionEdge, data: dict) -> bool:
    """An edge PATCH of connector/label/notes/ports is a change to the point it stands for.

    The edge already carries the new values (the caller applied the PATCH to it), so only the
    canonical point on the node (and an output's root entry) is updated; the edges are not rebuilt.
    """
    attrs = edge.attributes or {}
    point_id, chain = attrs.get("point_id"), attrs.get("chain")
    sent = data.get("attributes") or {}
    changed = {k: sent[k] or "" for k in POINT_KEYS if k in sent}
    if edge.signal != "video" or not point_id or not chain or not changed:
        return False
    node = await db.get(GraphDevice, uuid.UUID(chain))
    if node is None:
        return False
    attributes = dict(node.attributes or {})
    for key in ("points", "roots"):
        attributes[key] = [
            {**p, **changed} if p.get("point_id") == point_id else p
            for p in attributes.get(key, [])
        ]
    node.attributes = attributes
    await db.flush()
    return True


async def delete_edge_point(db: AsyncSession, edge: ConnectionEdge) -> bool:
    """Deleting a connection removes its point; an output's children move up to its parent."""
    attrs = edge.attributes or {}
    point_id, chain = attrs.get("point_id"), attrs.get("chain")
    if edge.signal != "video" or not point_id or not chain:
        return False
    node = await db.get(GraphDevice, uuid.UUID(chain))
    if node is None:
        return False
    points = (node.attributes or {}).get("points", [])
    gone = next((p for p in points if p["point_id"] == point_id), None)
    if gone is None:
        return False
    kept = [
        {**p, "parent_id": gone.get("parent_id")} if p.get("parent_id") == point_id else p
        for p in points
        if p["point_id"] != point_id
    ]
    await rebuild(db, node, kept)
    return True


async def clear_references(db: AsyncSession, node: GraphDevice) -> tuple[list[str], list[str]]:
    """What pointed at a video node by id (plot links, a switcher's list) is cleared with it.

    Deleting a list deletes its inputs and outputs too. Returns the ids of the child nodes and of
    the edges removed with them, for the caller to publish.
    """
    ref = public_id(node)
    removed_nodes: list[str] = []
    removed_edges: list[str] = []
    if node.kind == "video_input":
        await db.execute(
            update(StagePlotElement)
            .where(StagePlotElement.linked_video_input_id == ref)
            .values(linked_video_input_id=None)
        )
    elif node.kind == "video_list":
        await db.execute(
            update(AudioDevice).where(AudioDevice.video_list_id == ref).values(video_list_id=None)
        )
        children = [
            c
            for c in (
                await db.scalars(
                    select(GraphDevice).where(
                        GraphDevice.job_id == node.job_id, GraphDevice.domain == "video"
                    )
                )
            ).all()
            if (c.attributes or {}).get("list_id") == str(node.id)
        ]
        edges = (
            await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == node.job_id))
        ).all()
        for child in children:
            await clear_references(db, child)
            for edge in edges:
                if child.id in (edge.src_device_id, edge.dst_device_id):
                    removed_edges.append(str(edge.id))
                    await db.delete(edge)
            removed_nodes.append(str(child.id))
            await db.delete(child)
    return removed_nodes, removed_edges


async def require_step_devices(db: AsyncSession, job_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    for device_id in ids:
        node = await db.get(GraphDevice, device_id)
        if node is None or node.job_id != job_id or node.kind in VIDEO_KINDS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job"
            )


def video_input_node(
    job_id: uuid.UUID, list_node: GraphDevice, data: dict, legacy_id: uuid.UUID | None = None
) -> GraphDevice:
    number = data["input_number"]
    connector = data.get("connector") or ""
    return GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id,
        domain="video",
        kind="video_input",
        name=data.get("source_label") or f"Input {number}",
        notes=data.get("notes") or "",
        position=number,
        attributes={
            "input_number": number,
            "source_type": data.get("source_type") or "camera",
            "source_label": data.get("source_label") or "",
            "stockwire_product_id": data.get("stockwire_product_id"),
            "stockwire_product_name": data.get("stockwire_product_name"),
            "connector": connector,
            "list_id": str(list_node.id),
            "points": [],
            **({"legacy_id": str(legacy_id)} if legacy_id else {}),
        },
        ports=[
            {
                "id": "out",
                "direction": "out",
                "signal": "video",
                "connector": connector.lower() or None,
            }
        ],
    )


def video_output_node(
    job_id: uuid.UUID, list_node: GraphDevice, data: dict, legacy_id: uuid.UUID | None = None
) -> GraphDevice:
    number = data["output_number"]
    connector = data.get("connector") or ""
    return GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id,
        domain="video",
        kind="video_destination",
        name=data.get("destination_label") or data.get("name") or f"Output {number}",
        notes=data.get("notes") or "",
        position=number,
        attributes={
            "output_number": number,
            "name": data.get("name") or "",
            "destination_label": data.get("destination_label") or "",
            "connector": connector,
            "list_id": str(list_node.id),
            "points": [],
            "roots": [],
            **({"legacy_id": str(legacy_id)} if legacy_id else {}),
        },
        ports=[
            {
                "id": "in",
                "direction": "in",
                "signal": "video",
                "connector": connector.lower() or None,
                "channels": 1,
            }
        ],
    )


# ---- one-off import of the legacy video tables ------------------------------------------------


def is_legacy_video_ref(ref: str | None) -> bool:
    return bool(ref) and ref.startswith(LEGACY_VIDEO_REFS)


async def import_legacy(db: AsyncSession, job_id: uuid.UUID) -> bool:
    """Bring a job's rows from the legacy video tables onto the graph. True if anything changed.

    The graph is synced lazily per job, so a job's video may be a mirror node (``legacy_ref``),
    not on the graph at all yet, or already native (``attributes.legacy_id``). This makes every
    legacy list, input and output a native node: the legacy id becomes ``attributes.legacy_id``
    (its public id, so cable keys, plot links and ``video_list_id`` stay valid), the points are
    taken from the patch point tables (a repeated device included) and the edges are rebuilt. A row
    that is already native is left alone, so graph edits are never overwritten. It reads the
    tables only to import; once every job has been imported (``scripts/import_legacy_video.py``)
    the tables can be dropped and this goes with them.
    """
    from sqlalchemy.orm import selectinload

    from app.domains.video.models import VideoInput, VideoInputList, VideoOutput

    lists = (
        await db.scalars(
            select(VideoInputList)
            .where(VideoInputList.job_id == job_id)
            .options(
                selectinload(VideoInputList.inputs).selectinload(VideoInput.patch_points),
                selectinload(VideoInputList.outputs).selectinload(VideoOutput.patch_points),
            )
        )
    ).all()
    if not lists:
        return False
    nodes = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == job_id,
                GraphDevice.kind.in_(VIDEO_KINDS),
            )
        )
    ).all()
    by_public = {public_id(n): n for n in nodes}
    device_node = {
        uuid.UUID(d.legacy_ref.partition(":")[2]): d.id
        for d in (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.legacy_ref.like("audio_devices:%")
                )
            )
        ).all()
    }

    def done(node: GraphDevice | None) -> bool:
        return node is not None and not node.legacy_ref and "legacy_id" in (node.attributes or {})

    def adopt(node: GraphDevice, legacy_id: uuid.UUID) -> None:
        node.legacy_ref = None
        node.attributes = {**(node.attributes or {}), "legacy_id": str(legacy_id)}

    changed = False
    for lst in lists:
        list_node = by_public.get(lst.id)
        if not done(list_node):
            changed = True
            attrs = {
                "switcher_product_id": lst.switcher_product_id,
                "switcher_product_name": lst.switcher_product_name,
                "switcher_inputs": lst.switcher_inputs,
                "switcher_outputs": lst.switcher_outputs,
                "legacy_id": str(lst.id),
            }
            if list_node is None:
                list_node = GraphDevice(
                    id=uuid.uuid4(),
                    job_id=job_id,
                    domain="video",
                    kind="video_list",
                    name=lst.name,
                    position=lst.position,
                    stockwire_product_id=lst.switcher_product_id,
                    stockwire_product_name=lst.switcher_product_name,
                    attributes=attrs,
                )
                db.add(list_node)
            else:
                list_node.legacy_ref = None
                list_node.attributes = {**(list_node.attributes or {}), **attrs}
            await db.flush()
        rows = [(vin, "video_input", video_input_node) for vin in lst.inputs] + [
            (vout, "video_destination", video_output_node) for vout in lst.outputs
        ]
        for row, kind, make in rows:
            node = by_public.get(row.id)
            if done(node):
                continue
            changed = True
            if kind == "video_input":
                data = {
                    "input_number": row.input_number,
                    "source_label": row.source_label,
                    "source_type": row.source_type,
                    "connector": row.connector,
                    "notes": row.notes,
                    "stockwire_product_id": row.stockwire_product_id,
                    "stockwire_product_name": row.stockwire_product_name,
                }
            else:
                data = {
                    "output_number": row.output_number,
                    "name": row.name,
                    "destination_label": row.destination_label,
                    "connector": row.connector,
                    "notes": row.notes,
                }
            fresh = make(job_id, list_node, data, legacy_id=row.id)
            if node is None:
                node = fresh
                db.add(node)
            else:
                # a mirror node keeps its id (the web app and links may hold it); its content is
                # taken from the row
                node.name, node.notes, node.position = fresh.name, fresh.notes, fresh.position
                node.attributes, node.ports, node.legacy_ref = fresh.attributes, fresh.ports, None
            await db.flush()
            old = (
                await db.scalars(
                    select(ConnectionEdge).where(
                        ConnectionEdge.job_id == job_id, ConnectionEdge.signal == "video"
                    )
                )
            ).all()
            for edge in old:
                attrs = edge.attributes or {}
                if is_legacy_video_ref(attrs.get("legacy_ref")) and (
                    attrs.get("chain") == str(node.id) or edge.dst_device_id == node.id
                ):
                    await db.delete(edge)
            await db.flush()
            points = []
            for point in sorted(row.patch_points, key=lambda p: p.position):
                target = device_node.get(point.device_id)
                if target is None:
                    continue
                points.append(
                    {
                        "point_id": str(point.id),
                        "position": point.position or 0,
                        "device_id": str(target),
                        "parent_id": str(point.parent_id)
                        if getattr(point, "parent_id", None)
                        else None,
                        **{key: getattr(point, key, "") or "" for key in POINT_KEYS},
                    }
                )
            await rebuild(db, node, points)
            by_public[row.id] = node
    if changed:
        await db.commit()
    return changed
