"""Video lists as the rest of the backend reads them, built from the graph instead of the tables.

The video domain's consumers (the Stockwire sync, the cable derivation, per-device input/output
counts, the patch sheets) used to read ``video_input_lists`` and its children. These readers give
them the same shapes from ``graph_devices``/``graph_connection_edges``, so the legacy tables can be
dropped. The ids are still the legacy ids (carried by ``legacy_ref``): saved cable routes, plot
element links and report layouts are keyed by them, and they stay valid until the final migration
rewrites those keys.

How a chain is stored (see ``backfill.Builder.video``): an input's patch points are the edges
whose ``attributes.chain`` is the input node, in ``position`` order, each ending on the device the
point names; an output's *root* points have no edge of their own (they are listed in the
destination's ``attributes.roots``) and its other points are edges with a ``parent_id``.
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.backfill import backfill_job
from app.domains.graph.mirror import legacy_target
from app.domains.graph.models import ConnectionEdge, GraphDevice


def _legacy_id(row) -> uuid.UUID | None:
    target = legacy_target(row)
    return target[1] if target else None


def _point(attrs: dict, device_id: uuid.UUID | None, **owner) -> SimpleNamespace:
    parent = attrs.get("parent_id")
    return SimpleNamespace(
        id=uuid.UUID(attrs["point_id"]),
        position=attrs.get("position") or 0,
        connector=attrs.get("connector") or "",
        patch_label=attrs.get("patch_label") or "",
        notes=attrs.get("notes") or "",
        source_port=attrs.get("source_port") or "",
        input_port=attrs.get("input_port") or "",
        parent_id=uuid.UUID(parent) if parent else None,
        device_id=device_id,
        **owner,
    )


async def load_video_lists(db: AsyncSession, job_id: uuid.UUID) -> list[SimpleNamespace]:
    """Every video list of a job with its inputs, outputs and their patch points, ordered."""
    await backfill_job(db, job_id)
    nodes = (
        await db.scalars(
            select(GraphDevice).where(GraphDevice.job_id == job_id, GraphDevice.domain == "video")
        )
    ).all()
    gear = {
        d.id: _legacy_id(d)
        for d in (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.legacy_ref.like("audio_devices:%")
                )
            )
        ).all()
    }
    edges = (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == job_id, ConnectionEdge.signal == "video"
            )
        )
    ).all()
    chains: dict[str, list[ConnectionEdge]] = {}
    for edge in edges:
        chain = (edge.attributes or {}).get("chain")
        if chain and (edge.attributes or {}).get("point_id"):
            chains.setdefault(chain, []).append(edge)

    def points_of(node: GraphDevice, owner_key: str) -> list[SimpleNamespace]:
        owner = {owner_key: _legacy_id(node)}
        out = [
            _point(e.attributes, gear.get(e.dst_device_id), **owner)
            for e in chains.get(str(node.id), [])
        ]
        for root in (node.attributes or {}).get("roots") or []:
            if root.get("point_id"):
                out.append(_point(root, gear.get(uuid.UUID(root["device_id"])), **owner))
        return sorted(out, key=lambda p: p.position)

    lists: dict[str, SimpleNamespace] = {}
    for node in sorted(
        (n for n in nodes if n.kind == "video_list"), key=lambda n: (n.position, n.created_at)
    ):
        a = node.attributes or {}
        lists[str(node.id)] = SimpleNamespace(
            id=_legacy_id(node),
            job_id=job_id,
            name=node.name,
            position=node.position,
            switcher_product_id=a.get("switcher_product_id"),
            switcher_product_name=a.get("switcher_product_name"),
            switcher_inputs=a.get("switcher_inputs"),
            switcher_outputs=a.get("switcher_outputs"),
            inputs=[],
            outputs=[],
        )
    for node in nodes:
        a = node.attributes or {}
        owner = lists.get(a.get("list_id"))
        if owner is None:
            continue
        if node.kind == "video_input":
            owner.inputs.append(
                SimpleNamespace(
                    id=_legacy_id(node),
                    list_id=owner.id,
                    input_number=a.get("input_number") or 0,
                    source_label=a.get("source_label") or "",
                    source_type=a.get("source_type") or "camera",
                    connector=a.get("connector") or "",
                    notes=node.notes or "",
                    stockwire_product_id=a.get("stockwire_product_id"),
                    stockwire_product_name=a.get("stockwire_product_name"),
                    patch_points=points_of(node, "input_id"),
                )
            )
        elif node.kind == "video_destination":
            owner.outputs.append(
                SimpleNamespace(
                    id=_legacy_id(node),
                    list_id=owner.id,
                    output_number=a.get("output_number") or 0,
                    name=a.get("name") or "",
                    destination_label=a.get("destination_label") or "",
                    connector=a.get("connector") or "",
                    notes=node.notes or "",
                    patch_points=points_of(node, "output_id"),
                )
            )
    for lst in lists.values():
        lst.inputs.sort(key=lambda i: i.input_number)
        lst.outputs.sort(key=lambda o: o.output_number)
    return list(lists.values())


async def video_counts_per_device(db: AsyncSession, job_id: uuid.UUID) -> tuple[dict, dict]:
    """How many distinct video inputs and outputs are patched through each device (by legacy id)."""
    inputs: dict[str, set] = {}
    outputs: dict[str, set] = {}
    for lst in await load_video_lists(db, job_id):
        for vin in lst.inputs:
            for point in vin.patch_points:
                if point.device_id is not None:
                    inputs.setdefault(str(point.device_id), set()).add(vin.id)
        for vout in lst.outputs:
            for point in vout.patch_points:
                if point.device_id is not None:
                    outputs.setdefault(str(point.device_id), set()).add(vout.id)
    return (
        {k: len(v) for k, v in inputs.items()},
        {k: len(v) for k, v in outputs.items()},
    )


async def device_has_video_input_points(
    db: AsyncSession, job_id: uuid.UUID, device_id: uuid.UUID
) -> bool:
    """Whether a video input is patched through the device (it then cannot be deleted)."""
    return any(
        point.device_id == device_id
        for lst in await load_video_lists(db, job_id)
        for vin in lst.inputs
        for point in vin.patch_points
    )


def describe(lists) -> list[dict]:
    """Video lists as plain dicts, for comparing the table-backed and the graph-backed readers."""

    def point(p) -> dict:
        return {
            "id": str(p.id),
            "position": p.position,
            "connector": p.connector or "",
            "patch_label": p.patch_label or "",
            "notes": p.notes or "",
            "source_port": p.source_port or "",
            "input_port": p.input_port or "",
            "parent_id": str(p.parent_id) if getattr(p, "parent_id", None) else None,
            "device_id": str(p.device_id) if p.device_id else None,
        }

    def ordered(points) -> list[dict]:
        return sorted((point(p) for p in points), key=lambda p: (p["position"], p["id"]))

    return [
        {
            "id": str(lst.id),
            "name": lst.name,
            "position": lst.position,
            "switcher": [
                lst.switcher_product_id,
                lst.switcher_product_name,
                lst.switcher_inputs,
                lst.switcher_outputs,
            ],
            "inputs": [
                {
                    "id": str(i.id),
                    "number": i.input_number,
                    "label": i.source_label or "",
                    "type": i.source_type,
                    "connector": i.connector or "",
                    "notes": i.notes or "",
                    "product": [i.stockwire_product_id, i.stockwire_product_name],
                    "points": ordered(i.patch_points),
                }
                for i in sorted(lst.inputs, key=lambda i: (i.input_number, str(i.id)))
            ],
            "outputs": [
                {
                    "id": str(o.id),
                    "number": o.output_number,
                    "name": o.name or "",
                    "destination": o.destination_label or "",
                    "connector": o.connector or "",
                    "notes": o.notes or "",
                    "points": ordered(o.patch_points),
                }
                for o in sorted(lst.outputs, key=lambda o: (o.output_number, str(o.id)))
            ],
        }
        for lst in sorted(lists, key=lambda lst: (lst.position, str(lst.id)))
    ]
