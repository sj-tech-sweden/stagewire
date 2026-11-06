"""Rigging points on the graph (no legacy table behind them).

A ``rigging_point`` node (domain ``rigging``) holds ``attributes.trim_height_cm`` and
``attributes.weight_capacity_kg``; its name, position and notes are the node's. Loads refer to it by
its public id (``ids.public_id``): the ``rigging_point_id`` attribute of a device,
``lighting_fixtures`` and ``stage_plot_elements`` holds the legacy id for a point that came from
the old table and the node's own id for a new one. ``clear_references`` clears those columns when a
point is deleted, as ``ON DELETE SET NULL`` used to.
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.ids import public_id
from app.domains.graph.models import GraphDevice, scope_filter


def point_node(
    job_id: uuid.UUID | None, position: int, data: dict, legacy_id=None, venue_id=None
) -> GraphDevice:
    """A ``rigging_point`` graph node. Pass ``venue_id`` (and ``job_id=None``) to scope it to a
    venue's Standard Base Rig; with ``venue_id=None`` the job path is unchanged.
    """
    return GraphDevice(
        id=uuid.uuid4(),
        job_id=job_id,
        venue_id=venue_id,
        domain="rigging",
        kind="rigging_point",
        name=data.get("name") or "Rigging point",
        notes=data.get("notes") or "",
        position=position,
        attributes={
            **{
                k: data[k]
                for k in ("trim_height_cm", "weight_capacity_kg")
                if data.get(k) is not None
            },
            **({"legacy_id": str(legacy_id)} if legacy_id else {}),
        },
        ports=[],
    )


def point_view(node: GraphDevice) -> SimpleNamespace:
    """A rigging point as the weight summary and the load checks read it."""
    attrs = node.attributes or {}
    return SimpleNamespace(
        id=public_id(node),
        job_id=node.job_id,
        name=node.name,
        position=node.position,
        trim_height_cm=attrs.get("trim_height_cm"),
        weight_capacity_kg=attrs.get("weight_capacity_kg"),
        notes=node.notes or "",
    )


async def load_points(
    db: AsyncSession, job_id: uuid.UUID | None, venue_id: uuid.UUID | None = None
) -> list[SimpleNamespace]:
    rows = (
        await db.scalars(
            select(GraphDevice).where(
                scope_filter(GraphDevice, job_id, venue_id),
                GraphDevice.kind == "rigging_point",
            )
        )
    ).all()
    return [point_view(n) for n in sorted(rows, key=lambda n: (n.position, n.created_at))]


async def get_point(
    db: AsyncSession,
    job_id: uuid.UUID | None,
    point_id: uuid.UUID,
    venue_id: uuid.UUID | None = None,
) -> SimpleNamespace | None:
    return next((p for p in await load_points(db, job_id, venue_id) if p.id == point_id), None)


async def clear_references(
    db: AsyncSession, node: GraphDevice, venue_id: uuid.UUID | None = None
) -> None:
    # devices, fixtures and plot elements live on the graph: their link holds the point's node id.
    # Scope the scan to the node's own context so a job and a venue never cross-clear each other.
    for host in (
        await db.scalars(
            select(GraphDevice).where(
                scope_filter(GraphDevice, node.job_id, venue_id),
                GraphDevice.id != node.id,
            )
        )
    ).all():
        if (host.attributes or {}).get("rigging_point_id") == str(node.id):
            host.attributes = {k: v for k, v in host.attributes.items() if k != "rigging_point_id"}
