"""Graph-native rigging and power: rigging points, the power tree and load assignments.

The legacy rigging handlers hold the rules (connector checks, loops, overloads), so these
endpoints translate graph ids and call them; the graph is synced straight after.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import service
from app.domains.auth.deps import get_current_user
from app.domains.graph import schemas
from app.domains.graph.backfill import backfill_job, job_lock
from app.domains.graph.lists import _by_ref, _device_twin
from app.domains.graph.mirror import _fixtures_on_device, legacy_target
from app.domains.graph.models import GraphDevice
from app.domains.lighting.models import LightingFixture
from app.domains.rigging import router as rigging_router
from app.domains.rigging import schemas as rigging_schemas
from app.domains.rigging.models import PowerNode

router = APIRouter(
    prefix="/jobs/{job_id}/graph",
    tags=["graph:rigging"],
    dependencies=[Depends(get_current_user)],
)


class RiggingPointCreate(BaseModel):
    name: str = ""
    trim_height_cm: float | None = None
    weight_capacity_kg: float | None = None
    notes: str = ""


class PowerOutputBody(BaseModel):
    connector: str
    count: int = 1
    phase: str | None = None


class PowerNodeCreate(BaseModel):
    name: str = ""
    kind: str = "distro"
    parent_id: UUID | None = None
    feed_connector: str = ""
    phase: str | None = None
    outputs: list[PowerOutputBody] = []
    rating_amps: float | None = None
    active: bool = True
    venue_outlet_id: UUID | None = None
    device_id: UUID | None = None
    notes: str = ""


class FeedCreate(BaseModel):
    parent_id: UUID
    feed_connector: str = ""
    phase: str | None = None


class LoadAssign(BaseModel):
    load_id: UUID | None = None
    rigging_point_id: UUID | None = None
    power_node_id: UUID | None = None
    power_connector: str | None = None


async def _job(db: AsyncSession, job_id: UUID) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")


async def _legacy(
    db: AsyncSession, job_id: UUID, node_id: UUID | None, table: str, label: str
) -> UUID | None:
    if node_id is None:
        return None
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label} not found")
    target = legacy_target(node)
    if target is not None and target[0] == table:
        return target[1]
    if table == "power_nodes" and target is not None and target[0] == "audio_devices":
        found = await db.scalar(select(PowerNode.id).where(PowerNode.device_id == target[1]))
        if found is not None:
            return found
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"That is not a {label.lower()}")


@router.post("/rigging-points", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_rigging_point(
    job_id: UUID, payload: RiggingPointCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    await _job(db, job_id)
    body = rigging_schemas.RiggingPointCreate(**payload.model_dump())
    point = await rigging_router.create_point(job_id, body, db)
    await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(
        await _by_ref(db, job_id, f"rigging_points:{point.id}")
    )


@router.post("/power-nodes", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_power_node(
    job_id: UUID, payload: PowerNodeCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    await _job(db, job_id)
    data = payload.model_dump()
    data["parent_id"] = await _legacy(db, job_id, payload.parent_id, "power_nodes", "Parent node")
    if payload.device_id is not None:
        data["device_id"] = await _device_twin(db, job_id, payload.device_id)
    node = await rigging_router.create_node(job_id, rigging_schemas.PowerNodeCreate(**data), db)
    await backfill_job(db, job_id)
    row = await db.scalar(select(PowerNode).where(PowerNode.id == UUID(str(node["id"]))))
    ref = f"audio_devices:{row.device_id}" if row and row.device_id else f"power_nodes:{node['id']}"
    return schemas.GraphDeviceRead.model_validate(await _by_ref(db, job_id, ref))


@router.post(
    "/power-nodes/{node_id}/feeds", response_model=schemas.GraphDeviceRead, status_code=201
)
async def add_power_feed(
    job_id: UUID, node_id: UUID, payload: FeedCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    await _job(db, job_id)
    child = await _legacy(db, job_id, node_id, "power_nodes", "Power node")
    parent = await _legacy(db, job_id, payload.parent_id, "power_nodes", "Parent node")
    await rigging_router.add_feed(
        job_id,
        child,
        rigging_schemas.PowerNodeFeedCreate(
            parent_id=parent, feed_connector=payload.feed_connector, phase=payload.phase
        ),
        db,
    )
    await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(await db.get(GraphDevice, node_id))


async def _load_target(db: AsyncSession, job_id: UUID, node: GraphDevice) -> tuple[str, UUID]:
    target = legacy_target(node)
    if target is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node cannot carry a load")
    table, legacy_id = target
    if table == "stage_plot_elements":
        return "element", legacy_id
    if table == "lighting_fixtures":
        return "fixture", legacy_id
    if table == "audio_devices":
        fixtures = await _fixtures_on_device(db, job_id, legacy_id)
        if fixtures:
            return "fixture", fixtures[-1].id
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Only fixtures and plot elements carry loads"
    )


@router.put("/loads/{node_id}", response_model=schemas.GraphDeviceRead)
async def assign_load(
    job_id: UUID, node_id: UUID, payload: LoadAssign, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Hang a fixture or plot element on a rigging point and/or plug it into a power node."""
    await _job(db, job_id)
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found")
    kind, load_id = await _load_target(db, job_id, node)
    data = payload.model_dump(exclude_unset=True)
    chosen = data.pop("load_id", None)
    if chosen is not None:
        if kind == "fixture" and chosen not in {
            f.id for f in await _fixtures_on_device(db, job_id, legacy_target(node)[1])
        } | {legacy_target(node)[1]}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Load is not on that node")
        load_id = chosen if kind == "fixture" else load_id
    if "rigging_point_id" in data:
        data["rigging_point_id"] = await _legacy(
            db, job_id, data["rigging_point_id"], "rigging_points", "Rigging point"
        )
    if "power_node_id" in data:
        data["power_node_id"] = await _legacy(
            db, job_id, data["power_node_id"], "power_nodes", "Power node"
        )
    async with job_lock(job_id):
        await rigging_router.assign_load(
            job_id, kind, load_id, rigging_schemas.LoadAssign(**data), db
        )
    db.expire_all()
    await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(await db.get(GraphDevice, node_id))


async def _id_map(db: AsyncSession, job_id: UUID) -> dict[str, str]:
    """Legacy id (as the legacy summary prints it) -> graph node id."""
    rows = (await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))).all()
    by_ref = {r.legacy_ref: str(r.id) for r in rows if r.legacy_ref}
    out = {ref.partition(":")[2]: gid for ref, gid in by_ref.items()}
    for node in (await db.scalars(select(PowerNode).where(PowerNode.job_id == job_id))).all():
        if node.device_id and f"audio_devices:{node.device_id}" in by_ref:
            out[str(node.id)] = by_ref[f"audio_devices:{node.device_id}"]
    for fx in (
        await db.scalars(select(LightingFixture).where(LightingFixture.job_id == job_id))
    ).all():
        if fx.device_id and f"audio_devices:{fx.device_id}" in by_ref:
            out[str(fx.id)] = by_ref[f"audio_devices:{fx.device_id}"]
    return out


@router.get("/rigging/summary")
async def rigging_summary(job_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Weights per rigging point, power per node and every load, keyed by graph node id.

    A load keeps its legacy ``load_id`` and ``kind`` (what ``PUT /loads`` resolves from a node);
    ``id`` is the graph node it sits on.
    """
    await _job(db, job_id)
    summary = await rigging_router.rigging_summary(job_id, db)
    ids = await _id_map(db, job_id)
    mapped = lambda value: ids.get(str(value)) if value else None  # noqa: E731
    points = [{**p, "id": mapped(p["id"]) or p["id"]} for p in summary["points"]]
    nodes = [
        {
            **n,
            "id": mapped(n["id"]) or n["id"],
            "parent_id": mapped(n["parent_id"]),
            "parent_ids": [mapped(p) for p in n["parent_ids"]],
        }
        for n in summary["nodes"]
    ]
    loads = [
        {
            **load,
            "load_id": load["id"],
            "id": mapped(load["id"]) or load["id"],
            "rigging_point_id": mapped(load["rigging_point_id"]),
            "power_node_id": mapped(load["power_node_id"]),
            "device_id": mapped(load["device_id"]),
        }
        for load in summary["loads"]
    ]
    return {**summary, "points": points, "nodes": nodes, "loads": loads}
