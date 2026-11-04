"""Venue Standard Base Rig: a graph owned by a venue, cloned onto jobs.

A venue's Standard Base Rig is the set of graph devices and connection edges that belong to the
venue itself rather than to a specific production job. It lives in the same unified ``graph_*``
tables the jobs use (rows carry ``venue_id`` and a NULL ``job_id``), so the rig reuses the whole
graph editing UX. When a venue is assigned to a job, :func:`clone_base_rig_to_job` copies the rig
into that job, giving each device/edge a fresh id and clearing ``venue_id``.
"""

from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.graph.schemas import (
    ConnectionEdgeRead,
    GraphDeviceRead,
    GraphRead,
)
from app.domains.venues.schemas import VenueBaseRigWrite


async def get_base_rig(db: AsyncSession, venue_id: UUID) -> GraphRead:
    devices = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None)
            )
        )
    ).all()
    edges = (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.venue_id == venue_id, ConnectionEdge.job_id.is_(None)
            )
        )
    ).all()
    return GraphRead(
        devices=[GraphDeviceRead.model_validate(d) for d in devices],
        edges=[ConnectionEdgeRead.model_validate(e) for e in edges],
    )


async def replace_base_rig(
    db: AsyncSession, venue_id: UUID, payload: VenueBaseRigWrite
) -> GraphRead:
    # Drop the existing rig first; edges reference devices, so remove them before the devices.
    await db.execute(
        delete(ConnectionEdge).where(
            ConnectionEdge.venue_id == venue_id, ConnectionEdge.job_id.is_(None)
        )
    )
    await db.execute(
        delete(GraphDevice).where(GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None))
    )

    for device in payload.devices:
        db.add(
            GraphDevice(
                id=device.id,
                venue_id=venue_id,
                job_id=None,
                domain=device.domain,
                kind=device.kind,
                name=device.name,
                notes=device.notes,
                position=device.position,
                attributes=device.attributes,
                ports=[p.model_dump() for p in device.ports],
                canvas_x_cm=device.canvas_x_cm,
                canvas_y_cm=device.canvas_y_cm,
                canvas_rotation=device.canvas_rotation,
                case_parent_id=device.case_parent_id,
                stockwire_product_id=device.stockwire_product_id,
                stockwire_product_name=device.stockwire_product_name,
                stockwire_device_id=device.stockwire_device_id,
                stockwire_booked=device.stockwire_booked,
                legacy_ref=f"device:{device.id}",
                revision=1,
            )
        )
    for edge in payload.edges:
        db.add(
            ConnectionEdge(
                id=edge.id,
                venue_id=venue_id,
                job_id=None,
                signal=edge.signal,
                src_device_id=edge.src_device_id,
                src_port=edge.src_port,
                dst_device_id=edge.dst_device_id,
                dst_port=edge.dst_port,
                channels=edge.channels,
                phase=edge.phase,
                cable_label=edge.cable_label,
                notes=edge.notes,
                attributes=edge.attributes,
                graph_edited=False,
                revision=1,
            )
        )
    await db.commit()
    return await get_base_rig(db, venue_id)


def _remap_id(value: object, id_map: dict[UUID, UUID]) -> object:
    """If ``value`` is an old device id present in the map, return the new id."""
    if isinstance(value, str):
        try:
            as_uuid = UUID(value)
        except ValueError:
            return value
        if as_uuid in id_map:
            return str(id_map[as_uuid])
    elif isinstance(value, UUID) and value in id_map:
        return id_map[value]
    return value


async def clone_base_rig_to_job(db: AsyncSession, venue_id: UUID, job_id: UUID) -> int:
    """Copy the venue's rig into ``job_id``. Returns the number of devices cloned.

    Each device/edge gets a fresh id; ``venue_id`` is cleared so the clone reads as a normal job
    graph. Ids referenced inside edge endpoints and device attributes (e.g. a rigging point or
    power node the rig links to) are remapped to their cloned counterparts.
    """
    devices = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None)
            )
        )
    ).all()
    if not devices:
        return 0

    id_map: dict[UUID, UUID] = {}
    for device in devices:
        new_id = uuid4()
        id_map[device.id] = new_id
        db.add(
            GraphDevice(
                id=new_id,
                venue_id=None,
                job_id=job_id,
                domain=device.domain,
                kind=device.kind,
                name=device.name,
                notes=device.notes,
                position=device.position,
                attributes={k: _remap_id(v, id_map) for k, v in (device.attributes or {}).items()},
                ports=list(device.ports or []),
                canvas_x_cm=device.canvas_x_cm,
                canvas_y_cm=device.canvas_y_cm,
                canvas_rotation=device.canvas_rotation,
                case_parent_id=(
                    id_map[device.case_parent_id]
                    if device.case_parent_id in id_map
                    else device.case_parent_id
                ),
                stockwire_product_id=device.stockwire_product_id,
                stockwire_product_name=device.stockwire_product_name,
                stockwire_device_id=device.stockwire_device_id,
                stockwire_booked=device.stockwire_booked,
                legacy_ref=f"device:{new_id}",
                revision=1,
            )
        )

    edges = (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.venue_id == venue_id, ConnectionEdge.job_id.is_(None)
            )
        )
    ).all()
    for edge in edges:
        db.add(
            ConnectionEdge(
                id=uuid4(),
                venue_id=None,
                job_id=job_id,
                signal=edge.signal,
                src_device_id=id_map[edge.src_device_id],
                src_port=edge.src_port,
                dst_device_id=id_map[edge.dst_device_id],
                dst_port=edge.dst_port,
                channels=edge.channels,
                phase=edge.phase,
                cable_label=edge.cable_label,
                notes=edge.notes,
                attributes=edge.attributes or {},
                graph_edited=edge.graph_edited,
                revision=1,
            )
        )
    await db.commit()
    return len(devices)
