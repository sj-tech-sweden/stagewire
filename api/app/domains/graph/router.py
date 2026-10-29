from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.versioning import run_versioned_delete, run_versioned_write
from app.domains.audio.models import ProductionJob
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.graph import schemas, topology
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.stockwire.client import StockwireClient
from app.domains.stockwire.config import load_integration_config

router = APIRouter(
    prefix="/jobs/{job_id}/graph", tags=["graph"], dependencies=[Depends(get_current_user)]
)

MAX_BATCH = 200


async def get_stockwire_client(db: AsyncSession = Depends(get_db)) -> StockwireClient:
    cfg = await load_integration_config(db)
    return StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])


def _as_dict(row: GraphDevice | ConnectionEdge) -> dict:
    return {column.key: getattr(row, column.key) for column in row.__mapper__.column_attrs}


async def _require_job(db: AsyncSession, job_id: UUID) -> None:
    if await db.get(ProductionJob, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")


async def _device(db: AsyncSession, job_id: UUID, device_id: UUID) -> GraphDevice:
    device = await db.get(GraphDevice, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


async def _edge(db: AsyncSession, job_id: UUID, edge_id: UUID) -> ConnectionEdge:
    edge = await db.get(ConnectionEdge, edge_id)
    if edge is None or edge.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edge not found")
    return edge


async def _all_edges(db: AsyncSession, job_id: UUID) -> list[ConnectionEdge]:
    return list(
        (await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))).all()
    )


async def _all_devices(db: AsyncSession, job_id: UUID) -> list[GraphDevice]:
    return list(
        (
            await db.scalars(
                select(GraphDevice)
                .where(GraphDevice.job_id == job_id)
                .order_by(GraphDevice.position, GraphDevice.created_at)
            )
        ).all()
    )


def _device_payload(device: GraphDevice) -> dict:
    return schemas.GraphDeviceRead.model_validate(device).model_dump(mode="json")


@router.get("", response_model=schemas.GraphRead)
async def get_graph(job_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.GraphRead:
    await _require_job(db, job_id)
    return schemas.GraphRead(
        devices=[schemas.GraphDeviceRead.model_validate(d) for d in await _all_devices(db, job_id)],
        edges=[schemas.ConnectionEdgeRead.model_validate(e) for e in await _all_edges(db, job_id)],
    )


@router.post("/devices", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_device(
    job_id: UUID, payload: schemas.GraphDeviceCreate, db: AsyncSession = Depends(get_db)
) -> GraphDevice:
    await _require_job(db, job_id)
    device = GraphDevice(job_id=job_id, **payload.model_dump())
    db.add(device)
    await db.commit()
    await db.refresh(device)
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return device


@router.post("/devices/batch", response_model=list[schemas.GraphDeviceRead], status_code=201)
async def create_devices_batch(
    job_id: UUID, payload: list[schemas.GraphDeviceCreate], db: AsyncSession = Depends(get_db)
) -> list[GraphDevice]:
    await _require_job(db, job_id)
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} devices")
    devices = [GraphDevice(job_id=job_id, **item.model_dump()) for item in payload]
    db.add_all(devices)
    await db.commit()
    for device in devices:
        await db.refresh(device)
        await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return devices


@router.patch("/devices/{device_id}", response_model=schemas.GraphDeviceRead)
async def update_device(
    job_id: UUID,
    device_id: UUID,
    payload: schemas.GraphDeviceUpdate,
    db: AsyncSession = Depends(get_db),
) -> GraphDevice:
    device = await _device(db, job_id, device_id)
    data = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)

    async def apply() -> GraphDevice:
        for key, value in data.items():
            setattr(device, key, value)
        await db.commit()
        await db.refresh(device)
        return device

    device = await run_versioned_write(
        db,
        device,
        payload.expected_revision,
        schemas.GraphDeviceRead,
        apply,
        lambda: db.get(GraphDevice, device_id),
    )
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return device


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    job_id: UUID,
    device_id: UUID,
    expected_revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await _device(db, job_id, device_id)
    touching = [
        e for e in await _all_edges(db, job_id) if device_id in (e.src_device_id, e.dst_device_id)
    ]
    removed_edges = [str(e.id) for e in touching]

    async def remove() -> None:
        for edge in touching:
            await db.delete(edge)
        await db.delete(device)
        await db.commit()

    await run_versioned_delete(
        db,
        device,
        expected_revision,
        schemas.GraphDeviceRead,
        remove,
        lambda: db.get(GraphDevice, device_id),
    )
    await publish_job_event(
        job_id, "graph.device.delete", {"id": str(device_id), "edge_ids": removed_edges}
    )


@router.post("/edges", response_model=schemas.ConnectionEdgeRead, status_code=201)
async def create_edge(
    job_id: UUID,
    payload: schemas.ConnectionEdgeCreate,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> ConnectionEdge:
    src = await _device(db, job_id, payload.src_device_id)
    dst = await _device(db, job_id, payload.dst_device_id)
    existing = await _all_edges(db, job_id)
    if topology.would_create_cycle(
        [_as_dict(e) for e in existing if e.signal == payload.signal],
        str(src.id),
        str(dst.id),
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Connection would form a loop")
    issues = topology.validate_edge(
        payload.model_dump(mode="json"),
        _as_dict(src),
        _as_dict(dst),
        [_as_dict(e) for e in existing],
    )
    if issues and not force:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_connection",
                "issues": [schemas.IssueRead(**vars(i)).model_dump() for i in issues],
            },
        )
    edge = ConnectionEdge(job_id=job_id, **payload.model_dump())
    db.add(edge)
    await db.commit()
    await db.refresh(edge)
    await publish_job_event(
        job_id,
        "graph.edge.upsert",
        schemas.ConnectionEdgeRead.model_validate(edge).model_dump(mode="json"),
    )
    return edge


@router.patch("/edges/{edge_id}", response_model=schemas.ConnectionEdgeRead)
async def update_edge(
    job_id: UUID,
    edge_id: UUID,
    payload: schemas.ConnectionEdgeUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConnectionEdge:
    edge = await _edge(db, job_id, edge_id)
    data = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)

    async def apply() -> ConnectionEdge:
        for key, value in data.items():
            setattr(edge, key, value)
        await db.commit()
        await db.refresh(edge)
        return edge

    edge = await run_versioned_write(
        db,
        edge,
        payload.expected_revision,
        schemas.ConnectionEdgeRead,
        apply,
        lambda: db.get(ConnectionEdge, edge_id),
    )
    await publish_job_event(
        job_id,
        "graph.edge.upsert",
        schemas.ConnectionEdgeRead.model_validate(edge).model_dump(mode="json"),
    )
    return edge


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    job_id: UUID,
    edge_id: UUID,
    expected_revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> None:
    edge = await _edge(db, job_id, edge_id)

    async def remove() -> None:
        await db.delete(edge)
        await db.commit()

    await run_versioned_delete(
        db,
        edge,
        expected_revision,
        schemas.ConnectionEdgeRead,
        remove,
        lambda: db.get(ConnectionEdge, edge_id),
    )
    await publish_job_event(job_id, "graph.edge.delete", {"id": str(edge_id)})


@router.get("/devices/{device_id}/trace", response_model=schemas.TraceRead)
async def trace_device(
    job_id: UUID,
    device_id: UUID,
    direction: str = Query(pattern="^(upstream|downstream)$"),
    signal: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> schemas.TraceRead:
    await _device(db, job_id, device_id)
    edges = await _all_edges(db, job_id)
    devices = {str(d.id): _as_dict(d) for d in await _all_devices(db, job_id)}
    result = topology.trace([_as_dict(e) for e in edges], str(device_id), direction, signal=signal)
    by_id = {str(e.id): e for e in edges}
    issues = [
        i
        for hop in result.hops
        for i in topology.validate_edge(
            _as_dict(by_id[str(hop.edge["id"])]),
            devices.get(str(hop.edge["src_device_id"])),
            devices.get(str(hop.edge["dst_device_id"])),
            [_as_dict(e) for e in edges],
        )
    ]
    return schemas.TraceRead(
        root=result.root,
        direction=direction,
        truncated=result.truncated,
        hops=[
            schemas.HopRead(
                depth=h.depth,
                device_id=h.device_id,
                edge=schemas.ConnectionEdgeRead.model_validate(by_id[str(h.edge["id"])]),
            )
            for h in result.hops
        ],
        issues=[schemas.IssueRead(**vars(i)) for i in issues],
    )


@router.get("/validate", response_model=list[schemas.IssueRead])
async def validate_graph(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.IssueRead]:
    await _require_job(db, job_id)
    edges = await _all_edges(db, job_id)
    devices = {str(d.id): _as_dict(d) for d in await _all_devices(db, job_id)}
    rows = [_as_dict(e) for e in edges]
    return [
        schemas.IssueRead(**vars(issue))
        for row in rows
        for issue in topology.validate_edge(
            row,
            devices.get(str(row["src_device_id"])),
            devices.get(str(row["dst_device_id"])),
            rows,
        )
    ]


@router.get("/power-load", response_model=schemas.PhaseLoadRead)
async def power_load(job_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.PhaseLoadRead:
    await _require_job(db, job_id)
    devices = {str(d.id): _as_dict(d) for d in await _all_devices(db, job_id)}
    loads = topology.phase_loads(devices, [_as_dict(e) for e in await _all_edges(db, job_id)])
    peak, low = max(loads.values()), min(loads.values())
    return schemas.PhaseLoadRead(
        **loads, imbalance_pct=round((peak - low) / peak * 100, 1) if peak else 0.0
    )


@router.post("/devices/{device_id}/request-stockwire", response_model=schemas.GraphDeviceRead)
async def request_stockwire_booking(
    job_id: UUID,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    sw: StockwireClient = Depends(get_stockwire_client),
) -> GraphDevice:
    job = await db.get(ProductionJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    device = await _device(db, job_id, device_id)
    if not job.stockwire_job_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is not linked to a Stockwire job")
    if not device.stockwire_product_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Device is not bound to a Stockwire product"
        )
    if device.stockwire_booked:
        return device
    device.stockwire_request_status = "pending"
    await db.commit()
    await db.refresh(device)
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    try:
        await sw.add_requirement(
            job.stockwire_job_id,
            {
                "product_id": device.stockwire_product_id,
                "quantity_required": 1,
                "label": device.stockwire_product_name or device.name,
                "notes": f"Requested from Stagewire: {device.name}",
            },
        )
        device.stockwire_request_status = "requested"
        device.stockwire_booked = True
    except Exception:  # noqa: BLE001
        device.stockwire_request_status = "failed"
    await db.commit()
    await db.refresh(device)
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    if device.stockwire_request_status == "failed":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stockwire rejected the request")
    return device
