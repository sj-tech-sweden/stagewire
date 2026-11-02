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
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import fixtures_native, plot_native, power_native, rigging_native, schemas
from app.domains.graph.backfill import backfill_job, job_lock
from app.domains.graph.ids import power_id_of, public_id
from app.domains.graph.lists import _device_twin
from app.domains.graph.mirror import _fixtures_on_device, legacy_target
from app.domains.graph.models import GraphDevice
from app.domains.rigging import connectors
from app.domains.rigging import router as rigging_router
from app.domains.rigging import schemas as rigging_schemas
from app.domains.rigging import service as rigging_service
from app.domains.venues.models import VenuePowerGroup, VenuePowerOutlet

router = APIRouter(
    prefix="/jobs/{job_id}/graph",
    tags=["graph:rigging"],
    dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)],
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
    length_m: float | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


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
    if table == "power_nodes":
        found = power_id_of(node)  # the node hosts a power node: its public id
        if found is not None:
            return found
    if table == "rigging_points" and node.kind == "rigging_point":
        return public_id(
            node
        )  # rigging points have no legacy row; the public id is what loads hold
    target = legacy_target(node)
    if target is not None and target[0] == table:
        return target[1]
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"That is not a {label.lower()}")


@router.post("/rigging-points", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_rigging_point(
    job_id: UUID, payload: RiggingPointCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    await _job(db, job_id)
    async with job_lock(job_id):
        position = len(await rigging_native.load_points(db, job_id))
        node = rigging_native.point_node(job_id, position, payload.model_dump())
        db.add(node)
        await db.commit()
    await db.refresh(node)
    return schemas.GraphDeviceRead.model_validate(node)


class OutletSource(BaseModel):
    node: schemas.GraphDeviceRead
    connector: str


@router.post("/venue-power/outlets/{outlet_id}/source", response_model=OutletSource)
async def outlet_source(
    job_id: UUID, outlet_id: UUID, db: AsyncSession = Depends(get_db)
) -> OutletSource:
    """The power node that stands for a venue outlet, made on first use.

    An outlet in a group is served by one source node for the whole group: it carries the group's
    rating, so everything plugged into the group's outlets counts against it, and has one output
    per outlet connector (as many as there are outlets). An outlet without a group gets a source
    of its own with one output. Anything can then be fed from the returned node on ``connector``.
    """
    job = await service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    outlet = await db.get(VenuePowerOutlet, outlet_id)
    if outlet is None or job.venue_id is None or outlet.venue_id != job.venue_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outlet not found for this job's venue")
    if not outlet.connector or not connectors.known(outlet.connector):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the outlet a known connector first"
        )
    connector = outlet.connector
    async with job_lock(job_id):
        if outlet.group_id:
            node_id = await _group_source(db, job_id, outlet.group_id)
        else:
            node_id = await _single_outlet_source(db, job_id, outlet)
    host = await power_native.host_of(db, job_id, node_id)
    return OutletSource(node=schemas.GraphDeviceRead.model_validate(host), connector=connector)


async def _single_outlet_source(db: AsyncSession, job_id: UUID, outlet: VenuePowerOutlet) -> UUID:
    existing = await power_native.find_by_setting(db, job_id, "venue_outlet_id", outlet.id)
    if existing is not None:
        return existing.id
    created = await rigging_router.create_node(
        job_id,
        rigging_schemas.PowerNodeCreate(
            name=outlet.name or "Venue outlet",
            kind="source",
            feed_connector=outlet.connector,
            rating_amps=outlet.rating_amps,
            venue_outlet_id=outlet.id,
            outputs=[
                rigging_schemas.PowerOutput(
                    connector=outlet.connector,
                    count=1,
                    phase="L1" if connectors.connector(outlet.connector).phases == 1 else None,
                )
            ],
        ),
        db,
    )
    return UUID(str(created["id"]))


async def _group_source(db: AsyncSession, job_id: UUID, group_id: UUID) -> UUID:
    group = await db.get(VenuePowerGroup, group_id)
    outlets = (
        await db.scalars(select(VenuePowerOutlet).where(VenuePowerOutlet.group_id == group_id))
    ).all()
    counts: dict[str, int] = {}
    for item in outlets:
        if item.connector:
            counts[item.connector] = counts.get(item.connector, 0) + 1
    # A one-phase group puts all its load on one phase; a three-phase group is spread by the tree.
    phase = (group.phase or "L1") if group.phases == 1 else None
    outputs = [
        rigging_schemas.PowerOutput(connector=key, count=min(count, 99), phase=phase)
        for key, count in sorted(counts.items())
    ]
    existing = await power_native.find_by_setting(db, job_id, "venue_group_id", group_id)
    if existing is not None:
        await rigging_router.update_node(
            job_id,
            existing.id,
            rigging_schemas.PowerNodeUpdate(
                name=group.name or "Venue power",
                rating_amps=group.rating_amps,
                outputs=outputs,
            ),
            db,
        )
        return existing.id
    if not group.rating_amps:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Give the power group its rating (amps) before using it",
        )
    created = await rigging_router.create_node(
        job_id,
        rigging_schemas.PowerNodeCreate(
            name=group.name or "Venue power",
            kind="source",
            feed_connector="install_3p" if group.phases == 3 else "install_1p",
            rating_amps=group.rating_amps,
            outputs=outputs,
        ),
        db,
    )
    node_id = UUID(str(created["id"]))
    await power_native.update_node(db, job_id, node_id, {"venue_group_id": group_id})
    await db.commit()
    return node_id


@router.post("/power-nodes", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_power_node(
    job_id: UUID, payload: PowerNodeCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    await _job(db, job_id)
    data = payload.model_dump()
    data["parent_id"] = await _legacy(db, job_id, payload.parent_id, "power_nodes", "Parent node")
    if payload.device_id is not None:
        data["device_id"] = await _device_twin(db, job_id, payload.device_id)
    extra = {k: data.pop(k) for k in ("length_m", "stockwire_product_id", "stockwire_product_name")}
    node = await rigging_router.create_node(job_id, rigging_schemas.PowerNodeCreate(**data), db)
    host = await power_native.host_of(db, job_id, UUID(str(node["id"])))
    return await _decorate(db, host, extra)


async def _decorate(db: AsyncSession, node: GraphDevice, extra: dict) -> schemas.GraphDeviceRead:
    """Put what only the graph knows about a power node on it: the length of an extension cord
    (``length_m``) and the Stockwire product it is rented as."""
    if extra.get("length_m") is not None:
        node.attributes = {**node.attributes, "length_m": extra["length_m"]}
    for key in ("stockwire_product_id", "stockwire_product_name"):
        if extra.get(key) is not None:
            setattr(node, key, extra[key])
    await db.commit()
    await db.refresh(node)
    return schemas.GraphDeviceRead.model_validate(node)


class ParentMove(BaseModel):
    parent_id: UUID | None
    feed_connector: str = ""
    phase: str | None = None


@router.put("/power-nodes/{node_id}/parent", response_model=schemas.GraphDeviceRead)
async def move_power_node(
    job_id: UUID, node_id: UUID, payload: ParentMove, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Re-hang a node from another parent (and connector/phase), or cut its feed with no parent.

    The legacy update_node rules apply to a new parent: the connector must be an output of it and
    the tree may not loop."""
    await _job(db, job_id)
    legacy_id = await _legacy(db, job_id, node_id, "power_nodes", "Power node")
    if payload.parent_id is None:
        # Cutting the feed leaves the node unpowered; the legacy update would refuse that as an
        # error on the node, so the link is cleared directly.
        await power_native.update_node(
            db, job_id, legacy_id, {"parent_id": None, "feed_connector": "", "phase": None}
        )
        await db.commit()
        return schemas.GraphDeviceRead.model_validate(await db.get(GraphDevice, node_id))
    parent = await _legacy(db, job_id, payload.parent_id, "power_nodes", "Parent node")
    await rigging_router.update_node(
        job_id,
        legacy_id,
        rigging_schemas.PowerNodeUpdate(
            parent_id=parent, feed_connector=payload.feed_connector, phase=payload.phase
        ),
        db,
    )
    return schemas.GraphDeviceRead.model_validate(await db.get(GraphDevice, node_id))


class ExtensionInsert(BaseModel):
    length_m: float | None = None
    name: str = ""
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


@router.post(
    "/power-nodes/{node_id}/extension", response_model=schemas.GraphDeviceRead, status_code=201
)
async def insert_extension(
    job_id: UUID, node_id: UUID, payload: ExtensionInsert, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Put an extension cord ("skarvsladd") between a node and the parent that feeds it.

    The cord is a node of kind ``extension`` fed from the old parent on the node's feed connector
    and with one output of that same connector; the node is then re-hung from the cord. The
    legacy rules check both steps, so a node without a parent or feed connector is refused.
    """
    await _job(db, job_id)
    legacy_id = await _legacy(db, job_id, node_id, "power_nodes", "Power node")
    row = await rigging_service.get_node(db, job_id, legacy_id)
    if row is None or row.parent_id is None or not row.feed_connector:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a node with a feed can get an extension"
        )
    cord = await rigging_router.create_node(
        job_id,
        rigging_schemas.PowerNodeCreate(
            name=payload.name or "Extension",
            kind="extension",
            parent_id=row.parent_id,
            feed_connector=row.feed_connector,
            phase=row.phase,
            outputs=[
                rigging_schemas.PowerOutput(connector=row.feed_connector, count=1, phase=row.phase)
            ],
        ),
        db,
    )
    cord_id = UUID(str(cord["id"]))
    try:
        await rigging_router.update_node(
            job_id, legacy_id, rigging_schemas.PowerNodeUpdate(parent_id=cord_id), db
        )
    except HTTPException:
        await db.rollback()
        await rigging_router.delete_node(job_id, cord_id, db)
        raise
    return await _decorate(
        db,
        await power_native.host_of(db, job_id, cord_id),
        {
            "length_m": payload.length_m,
            "stockwire_product_id": payload.stockwire_product_id,
            "stockwire_product_name": payload.stockwire_product_name,
        },
    )


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
    return schemas.GraphDeviceRead.model_validate(await db.get(GraphDevice, node_id))


async def _load_target(db: AsyncSession, job_id: UUID, node: GraphDevice) -> tuple[str, UUID]:
    fixture_id = fixtures_native.fixture_id_of(node)
    if fixture_id is not None:  # a fixture's host: the fixture is the load (even on a device)
        return "fixture", fixture_id
    if plot_native.is_element(node):
        return "element", public_id(node)
    target = legacy_target(node)
    if target is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node cannot carry a load")
    table, legacy_id = target
    if table == "device":
        fixtures = await _fixtures_on_device(db, job_id, legacy_id)
        return ("fixture", fixtures[-1].id) if fixtures else ("device", legacy_id)
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Only gear and plot elements carry loads"
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
        allowed = {load_id}
        if node.legacy_ref and node.legacy_ref.startswith("device:"):
            allowed |= {f.id for f in await _fixtures_on_device(db, job_id, public_id(node))}
        if kind == "fixture" and chosen not in allowed:
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
    for row in rows:  # graph-native rows are known by their public id
        if row.kind == "rigging_point":
            out[str(public_id(row))] = str(row.id)
    for power_id, host in (await power_native.host_nodes(db, job_id)).items():
        out[str(power_id)] = str(host.id)
    for fid, host in (await fixtures_native.host_nodes(db, job_id)).items():
        out[str(fid)] = str(host.id)
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
