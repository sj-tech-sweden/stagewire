"""Video lists as the rest of the backend reads them, built from the graph instead of the tables.

The video domain's consumers (the Stockwire sync, the cable derivation, per-device input/output
counts, the patch sheets) used to read ``video_input_lists`` and its children. These readers give
them the same shapes from ``graph_devices``/``graph_connection_edges``, so the legacy tables can be
dropped. The ids are still the legacy ids (carried by ``legacy_ref``): saved cable routes, plot
element links and report layouts are keyed by them, and they stay valid until the final migration
rewrites those keys.

A chain is stored as the node's ``attributes.points`` (see ``video_native``); the edges are
derived from it.
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.backfill import backfill_job
from app.domains.graph.ids import public_id
from app.domains.graph.models import GraphDevice

_legacy_id = public_id


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


async def load_video_lists(
    db: AsyncSession, job_id: uuid.UUID, *, sync: bool = False
) -> list[SimpleNamespace]:
    """Every video list of a job with its inputs, outputs and their patch points, ordered.

    It reads the graph as it is: every write (legacy route or graph route) syncs the graph right
    after, and a sync of its own here would collide with a concurrent graph write (a stale-row
    error), so ``sync`` is only for a caller that has just changed legacy rows itself.
    """
    if sync:
        await backfill_job(db, job_id)
    nodes = (
        await db.scalars(
            select(GraphDevice).where(GraphDevice.job_id == job_id, GraphDevice.domain == "video")
        )
    ).all()
    # every device a chain can pass through, by node id; the point names the device's public id
    gear = {
        d.id: public_id(d)
        for d in (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id,
                    GraphDevice.kind.notin_(("video_list", "video_input", "video_destination")),
                )
            )
        ).all()
    }

    def points_of(node: GraphDevice, owner_key: str) -> list[SimpleNamespace]:
        owner = {owner_key: _legacy_id(node)}
        return sorted(
            (
                _point(p, gear.get(uuid.UUID(p["device_id"])), **owner)
                for p in (node.attributes or {}).get("points", [])
            ),
            key=lambda p: p.position,
        )

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
