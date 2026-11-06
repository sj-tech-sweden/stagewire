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
    """Additively copy the venue's rig into ``job_id``. Returns the number of devices added.

    Each device/edge gets a fresh id; ``venue_id`` is cleared so the clone reads as a normal job
    graph. Ids referenced inside edge endpoints and device attributes (e.g. a rigging point or
    power node the rig links to) are remapped to their cloned counterparts.

    The copy is **additive** so it can be re-run (e.g. on every "Update jobs" propagate) without
    clobbering a job's hand-edited graph:
    * a venue device already present in the job (matched by ``(domain, kind, name)``) is left
      untouched and its id is reused, so connecting edges stay correct;
    * only venue devices that are not already there are cloned in;
    * an edge is added only when both endpoints exist in the job afterwards and an equivalent edge
      (signal + endpoints + ports) is not already present.

    Matching by name (not a stored provenance id) keeps this schema-free; the only consequence is
    that renaming a job device after a first push makes it no longer "the same", so a later push
    would re-add the original-named venue device as a duplicate rather than skip it. That is a
    benign extra device, never an overwrite of the user's edited one.
    """
    venue_devices = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None)
            )
        )
    ).all()
    if not venue_devices:
        return 0

    job_devices = (
        await db.scalars(
            select(GraphDevice).where(GraphDevice.job_id == job_id, GraphDevice.venue_id.is_(None))
        )
    ).all()

    def match_key(d: GraphDevice) -> tuple:
        return (d.domain, d.kind, d.name)

    # Map an existing job device id per matched key; first wins so a single venue device never
    # maps onto two job devices.
    job_by_key: dict[tuple, UUID] = {}
    for jd in job_devices:
        job_by_key.setdefault(match_key(jd), jd.id)

    id_map: dict[UUID, UUID] = {}
    added_ids: list[UUID] = []
    for device in venue_devices:
        key = match_key(device)
        if key in job_by_key:
            # Already present in the job: reuse its id so edges connect to the existing node.
            id_map[device.id] = job_by_key[key]
            continue
        new_id = uuid4()
        id_map[device.id] = new_id
        added_ids.append(new_id)
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

    # Only add edges whose endpoints exist in the job (pre-existing or just added) and that are not
    # already present, so we never duplicate an edge or dangle one onto a skipped device.
    valid_ids = set(job_by_key.values()) | set(added_ids)
    venue_edges = (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.venue_id == venue_id, ConnectionEdge.job_id.is_(None)
            )
        )
    ).all()
    job_edges = (
        await db.scalars(
            select(ConnectionEdge).where(
                ConnectionEdge.job_id == job_id, ConnectionEdge.venue_id.is_(None)
            )
        )
    ).all()
    existing_edge_keys = {
        (e.signal, e.src_device_id, e.src_port, e.dst_device_id, e.dst_port) for e in job_edges
    }
    for edge in venue_edges:
        new_src = id_map.get(edge.src_device_id)
        new_dst = id_map.get(edge.dst_device_id)
        if new_src is None or new_dst is None:
            continue
        if new_src not in valid_ids or new_dst not in valid_ids:
            continue
        ekey = (edge.signal, new_src, edge.src_port, new_dst, edge.dst_port)
        if ekey in existing_edge_keys:
            continue
        db.add(
            ConnectionEdge(
                id=uuid4(),
                venue_id=None,
                job_id=job_id,
                signal=edge.signal,
                src_device_id=new_src,
                src_port=edge.src_port,
                dst_device_id=new_dst,
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
    return len(added_ids)
