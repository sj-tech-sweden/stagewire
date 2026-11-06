from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import replace as dc_replace
from types import SimpleNamespace
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import devices_native, fixtures_native, plot_native, power_native
from app.domains.graph.mirror import MirrorToGraphRoute
from app.domains.graph.models import belongs_to
from app.domains.lighting import service as lighting_service
from app.domains.rigging import calc, connectors, power_tree, schemas, service
from app.domains.venues import schemas as venue_schemas
from app.domains.venues.models import VenuePowerGroup, VenuePowerOutlet
from app.domains.venues.power_load import summarize_venue_power
from app.domains.venues.schemas import VenuePowerOutletRead

router = APIRouter(
    tags=["rigging"],
    dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)],
    route_class=MirrorToGraphRoute,
)

# A venue rig reuses the incremental power/rigging edits a job gets, but a venue has no legacy
# rows and no per-job websocket, so its endpoints use `dependencies=[Depends(get_current_user)]`
# only (no MirrorToGraphRoute, no refresh_power_connectors) and never touch the job-only machinery.
venue_router = APIRouter(
    prefix="/venues/{venue_id}",
    tags=["rigging:venue"],
    dependencies=[Depends(get_current_user)],
)


async def _job(db: AsyncSession, job_id: UUID):
    job = await audio_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    return job


async def _scope(db: AsyncSession, job_id: UUID | None = None, venue_id: UUID | None = None):
    """Resolve exactly one of job/venue and return ``(job, scope_venue_id)``.

    ``scope_venue_id`` is the venue whose power outlets/groups a node may reference: the job's
    venue for a job, the venue itself for a venue. Venues intentionally have no legacy rows.
    """
    if job_id is not None:
        job = await _job(db, job_id)
        return job, job.venue_id
    if venue_id is not None:
        from app.domains.venues import service as venue_service

        if await venue_service.get_venue(db, venue_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
        return None, venue_id
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "A job or a venue is required")


@asynccontextmanager
async def _scope_lock(job_id: UUID | None):
    """The job lock guards the legacy rows; a venue has none, so the block runs unlocked."""
    if job_id is not None:
        from app.domains.graph.backfill import job_lock

        async with job_lock(job_id):
            yield
    else:
        yield


async def _found(obj, detail: str):
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    return obj


def _outputs(items: list[schemas.PowerOutput]) -> list[dict]:
    return [{"connector": o.connector, "count": o.count, "phase": o.phase} for o in items]


def _check_connectors(node_outputs: list[dict], feed: str, rating: float | None) -> None:
    for output in node_outputs:
        if not connectors.known(output["connector"]):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown connector {output['connector']}"
            )
    if feed and not connectors.known(feed):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown connector {feed}")
    wiring = connectors.needs_rating(feed) or any(
        connectors.needs_rating(o["connector"]) for o in node_outputs
    )
    if wiring and not rating:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Installation wiring has no fixed rating: enter the cable's rating in amps",
        )


async def _check_device(
    db: AsyncSession, job_id: UUID | None, venue_id: UUID | None, device_id: UUID | None
) -> None:
    if device_id is None:
        return
    device = await audio_service.get_device(db, device_id, venue_id=venue_id)
    if device is None or not belongs_to(device, job_id, venue_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")


def _problems(evaluation: power_tree.Evaluation, *names: str) -> list[str]:
    """Errors that mention one of the given names (the node or load being changed)."""
    return [e for e in evaluation.errors if any(n and n in e for n in names)]


async def _reject(problems: list[str]) -> None:
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))


async def _read_node(
    db: AsyncSession, node, job_id: UUID | None = None, venue_id: UUID | None = None
) -> dict:
    # Validate the node before any further await expires its attributes in the async session.
    read = schemas.PowerNodeRead.model_validate(node)
    feeds = await service.list_feeds(db, job_id, venue_id)
    node_feeds = [f for f in feeds if str(f.node_id) == str(node.id)]
    read.feeds = [schemas.PowerNodeFeedRead.model_validate(f) for f in node_feeds]
    return read.model_dump(mode="json")


@router.get("/power-connectors")
@venue_router.get("/power-connectors")
async def list_connectors() -> list[dict]:
    return connectors.catalog()


@router.get("/jobs/{job_id}/power-outlets", response_model=list[VenuePowerOutletRead])
async def list_job_outlets(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await _job(db, job_id)
    return await service.venue_outlets(db, job.venue_id)


@router.get("/jobs/{job_id}/rigging-points", response_model=list[schemas.RiggingPointRead])
@venue_router.get("/rigging-points", response_model=list[schemas.RiggingPointRead])
async def list_points(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    await _scope(db, job_id, venue_id)
    return await service.list_points(db, job_id, venue_id)


@router.get("/jobs/{job_id}/power-nodes")
@venue_router.get("/power-nodes")
async def list_nodes(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _scope(db, job_id, venue_id)
    nodes = await service.list_nodes(db, job_id, venue_id)
    return [await _read_node(db, n, job_id, venue_id) for n in nodes]


@router.post(
    "/jobs/{job_id}/power-nodes",
    response_model=schemas.PowerNodeRead,
    status_code=status.HTTP_201_CREATED,
)
@venue_router.post(
    "/power-nodes",
    response_model=schemas.PowerNodeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_node(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    payload: schemas.PowerNodeCreate = None,
    db: AsyncSession = Depends(get_db),
):
    _job_or_none, scope_venue_id = await _scope(db, job_id, venue_id)
    data = payload.model_dump(exclude_unset=True)
    outputs = _outputs(payload.outputs)
    _check_connectors(outputs, payload.feed_connector, payload.rating_amps)
    await _check_device(db, job_id, venue_id, payload.device_id)
    if payload.kind == "source":
        if payload.parent_id is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A source has no parent")
    elif payload.parent_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Connect it to a parent node")
    if payload.venue_outlet_id is not None:
        outlet = await _found(
            await service.get_outlet(db, scope_venue_id, payload.venue_outlet_id),
            "Venue outlet not found for this job",
        )
        if outlet.connector != payload.feed_connector:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"The outlet is {outlet.connector}; the node is fed by {payload.feed_connector}",
            )
    nodes = await service.list_nodes(db, job_id, venue_id)
    feeds = await service.list_feeds(db, job_id, venue_id)
    rows = await service.collect_loads(db, job_id, venue_id)
    candidate = SimpleNamespace(
        id=UUID(int=0),
        job_id=job_id,
        parent_id=payload.parent_id,
        kind=payload.kind,
        name=payload.name or payload.kind,
        feed_connector=payload.feed_connector,
        phase=payload.phase,
        outputs=outputs,
        rating_amps=payload.rating_amps,
        active=payload.active,
    )
    tree = service.to_tree_nodes(nodes + [candidate], feeds)
    evaluation = power_tree.evaluate(tree, service.to_tree_loads(rows))
    await _reject(_problems(evaluation, candidate.name))
    node = await power_native.create_node(db, job_id, {**data, "outputs": outputs}, venue_id)
    await db.commit()
    return await _read_node(db, node, job_id, venue_id)


@router.get("/jobs/{job_id}/power-nodes/{node_id}", response_model=schemas.PowerNodeRead)
@venue_router.get("/power-nodes/{node_id}", response_model=schemas.PowerNodeRead)
async def get_power_node(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    node_id: UUID = None,
    db: AsyncSession = Depends(get_db),
):
    await _scope(db, job_id, venue_id)
    node = await _found(
        await service.get_node(db, job_id, node_id, venue_id), "Power node not found"
    )
    return await _read_node(db, node, job_id, venue_id)


@router.patch("/jobs/{job_id}/power-nodes/{node_id}", response_model=schemas.PowerNodeRead)
@venue_router.patch("/power-nodes/{node_id}", response_model=schemas.PowerNodeRead)
async def update_node(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    node_id: UUID = None,
    payload: schemas.PowerNodeUpdate = None,
    db: AsyncSession = Depends(get_db),
):
    await _scope(db, job_id, venue_id)
    node = await _found(
        await service.get_node(db, job_id, node_id, venue_id), "Power node not found"
    )
    data = payload.model_dump(exclude_unset=True)
    if "outputs" in data and data["outputs"] is not None:
        data["outputs"] = _outputs([schemas.PowerOutput(**o) for o in data["outputs"]])
    current = node
    current = node
    new_outputs = data["outputs"] if data.get("outputs") is not None else current.outputs or []
    _check_connectors(
        [{"connector": o["connector"], "count": o["count"]} for o in new_outputs],
        data.get("feed_connector") or current.feed_connector,
        data["rating_amps"] if "rating_amps" in data else current.rating_amps,
    )
    await _check_device(db, job_id, venue_id, data.get("device_id"))
    if data.get("venue_outlet_id") is not None:
        scope_venue_id = venue_id if venue_id is not None else (await _job(db, job_id)).venue_id
        await _found(
            await service.get_outlet(db, scope_venue_id, data["venue_outlet_id"]),
            "Venue outlet not found for this job",
        )
    nodes = await service.list_nodes(db, job_id, venue_id)
    feeds = await service.list_feeds(db, job_id, venue_id)
    rows = await service.collect_loads(db, job_id, venue_id)
    tree = service.to_tree_nodes(nodes, feeds)
    changed = {
        k: v
        for k, v in data.items()
        if k
        in {
            "parent_id",
            "feed_connector",
            "phase",
            "outputs",
            "rating_amps",
            "active",
            "name",
            "kind",
        }
    }
    if "outputs" in changed:
        changed["outputs"] = tuple(
            power_tree.Output(o["connector"], int(o["count"]), o.get("phase"))
            for o in changed["outputs"]
        )
    if "parent_id" in changed:
        if changed["parent_id"] is not None and str(changed["parent_id"]) in _descendant_ids(
            nodes, feeds, str(node.id)
        ) | {str(node.id)}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A node cannot hang from itself"
            )
        parent_id_value = str(changed["parent_id"]) if changed["parent_id"] else None
    else:
        parent_id_value = node.parent_id
    # power_tree.Node models the parent through `feeds`, not a `parent_id` column, so
    # rebuild the node's feeds (primary feed + extra merge feeds) for the evaluation tree.
    node_extra_feeds = [f for f in feeds if str(f.node_id) == str(node.id)]
    new_feeds: list[power_tree.Feed] = []
    if parent_id_value is not None:
        new_feeds.append(
            power_tree.Feed(
                str(parent_id_value),
                changed.get("feed_connector", node.feed_connector),
                changed.get("phase", node.phase),
            )
        )
    for f in node_extra_feeds:
        new_feeds.append(power_tree.Feed(str(f.parent_id), f.feed_connector, f.phase))
    replace_fields = {k: v for k, v in changed.items() if k != "parent_id"}
    replace_fields["feeds"] = tuple(new_feeds)
    tree = [dc_replace(n, **replace_fields) if n.id == str(node.id) else n for n in tree]
    if "name" in changed:
        names = (changed["name"], node.name)
    else:
        names = (node.name,)
    evaluation = power_tree.evaluate(tree, service.to_tree_loads(rows))
    await _reject(_problems(evaluation, *names))
    node = await power_native.update_node(db, job_id, node.id, data, venue_id)
    await db.commit()
    return await _read_node(
        db, await service.get_node(db, job_id, node.id, venue_id), job_id, venue_id
    )


def _descendant_ids(nodes: list, feeds: list, node_id: str) -> set[str]:
    children: dict[str, list[str]] = {}
    for n in nodes:
        if n.parent_id:
            children.setdefault(str(n.parent_id), []).append(str(n.id))
    for f in feeds:
        children.setdefault(str(f.parent_id), []).append(str(f.node_id))
    found: set[str] = set()
    stack = [node_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


@router.delete("/jobs/{job_id}/power-nodes/{node_id}", status_code=204)
@venue_router.delete("/power-nodes/{node_id}", status_code=204)
async def delete_node(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    node_id: UUID = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _scope(db, job_id, venue_id)
    node = await _found(
        await service.get_node(db, job_id, node_id, venue_id), "Power node not found"
    )
    nodes = await service.list_nodes(db, job_id, venue_id)
    feeds = await service.list_feeds(db, job_id, venue_id)
    if any(n.parent_id == node.id for n in nodes) or any(f.parent_id == node.id for f in feeds):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Move or remove the nodes fed from this one first"
        )
    rows = await service.collect_loads(db, job_id, venue_id)
    if any(r.power_node_id == str(node.id) for r in rows):
        raise HTTPException(status.HTTP_409_CONFLICT, "Unplug the loads on this node first")
    await power_native.delete_node(db, job_id, node.id, venue_id)
    await db.commit()


@router.post(
    "/jobs/{job_id}/power-nodes/{node_id}/feeds",
    response_model=schemas.PowerNodeFeedRead,
    status_code=status.HTTP_201_CREATED,
)
@venue_router.post(
    "/power-nodes/{node_id}/feeds",
    response_model=schemas.PowerNodeFeedRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_feed(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    node_id: UUID = None,
    payload: schemas.PowerNodeFeedCreate = None,
    db: AsyncSession = Depends(get_db),
):
    """Add an extra (merged) feed: power node ``node_id`` from ``parent_id``."""
    await _scope(db, job_id, venue_id)
    node = await _found(
        await service.get_node(db, job_id, node_id, venue_id), "Power node not found"
    )
    parent = await _found(
        await service.get_node(db, job_id, payload.parent_id, venue_id), "Parent node not found"
    )
    if parent.id == node.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A node cannot feed itself")
    if node.kind == "source":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A source has no parent")
    nodes = await service.list_nodes(db, job_id, venue_id)
    feeds = await service.list_feeds(db, job_id, venue_id)
    if str(parent.id) in _descendant_ids(nodes, feeds, str(node.id)) | {str(node.id)}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A node cannot hang from itself")
    if not connectors.known(payload.feed_connector):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown connector {payload.feed_connector}"
        )
    tree = service.to_tree_nodes(nodes, feeds)
    parent_tree = next((n for n in tree if n.id == str(parent.id)), None)
    if parent_tree is None or power_tree._output_for(parent_tree, payload.feed_connector) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{payload.feed_connector} is not an output of {parent.name}",
        )
    feed = SimpleNamespace(
        id=UUID(int=0),
        job_id=job_id,
        node_id=node.id,
        parent_id=parent.id,
        feed_connector=payload.feed_connector,
        phase=payload.phase,
    )
    rows = await service.collect_loads(db, job_id, venue_id)
    evaluation = power_tree.evaluate(
        service.to_tree_nodes(nodes, feeds + [feed]), service.to_tree_loads(rows)
    )
    await _reject(_problems(evaluation, node.name, parent.name))
    saved = await power_native.add_feed(
        db,
        job_id,
        node.id,
        parent.id,
        {"feed_connector": payload.feed_connector, "phase": payload.phase},
        venue_id,
    )
    await db.commit()
    return schemas.PowerNodeFeedRead.model_validate(saved)


@router.delete("/jobs/{job_id}/power-nodes/{node_id}/feeds/{feed_id}", status_code=204)
@venue_router.delete("/power-nodes/{node_id}/feeds/{feed_id}", status_code=204)
async def remove_feed(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    node_id: UUID = None,
    feed_id: UUID = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _scope(db, job_id, venue_id)
    await _found(await service.get_node(db, job_id, node_id, venue_id), "Power node not found")
    feeds = await service.list_feeds(db, job_id, venue_id)
    if not any(f.id == feed_id and f.node_id == node_id for f in feeds):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feed not found")
    await power_native.remove_feed(db, job_id, feed_id, venue_id)
    await db.commit()


@router.get("/jobs/{job_id}/rigging/loads", response_model=list[schemas.LoadRead])
@venue_router.get("/rigging/loads", response_model=list[schemas.LoadRead])
async def list_loads(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    await _scope(db, job_id, venue_id)
    return [
        schemas.LoadRead(
            id=UUID(r.id),
            kind=r.kind,
            label=r.label,
            weight_kg=r.weight_kg,
            power_w=r.power_w,
            rigging_point_id=UUID(r.rigging_point_id) if r.rigging_point_id else None,
            power_node_id=UUID(r.power_node_id) if r.power_node_id else None,
            power_connector=r.power_connector,
            device_id=UUID(r.device_id) if r.device_id else None,
        )
        for r in await service.collect_loads(db, job_id, venue_id)
    ]


@router.get("/jobs/{job_id}/rigging/summary")
@venue_router.get("/rigging/summary")
async def rigging_summary(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _scope(db, job_id, venue_id)
    points = [
        {"id": str(p.id), "name": p.name, "weight_capacity_kg": p.weight_capacity_kg}
        for p in await service.list_points(db, job_id, venue_id)
    ]
    rows = await service.collect_loads(db, job_id, venue_id)
    evaluation = power_tree.evaluate(
        service.to_tree_nodes(
            await service.list_nodes(db, job_id, venue_id),
            await service.list_feeds(db, job_id, venue_id),
        ),
        service.to_tree_loads(rows),
    )
    weights = calc.summarize_weights(points, service.weight_loads(rows))
    point_over = {str(p["id"]): bool(p["over"]) for p in weights}
    loads = []
    for r in rows:
        power = evaluation.loads.get(r.id, {})
        node = evaluation.nodes.get(r.power_node_id) if r.power_node_id else None
        loads.append(
            {
                "id": r.id,
                "kind": r.kind,
                "label": r.label,
                "weight_kg": r.weight_kg,
                "power_w": r.power_w,
                "rigging_point_id": r.rigging_point_id,
                "power_node_id": r.power_node_id,
                "power_connector": r.power_connector,
                "device_id": r.device_id,
                # hung on a point that carries more than its capacity is "over" for everything on it
                "rigging_status": (
                    "none"
                    if not r.rigging_point_id
                    else "over"
                    if point_over.get(r.rigging_point_id)
                    else "ok"
                ),
                # a load sits on its node: when the node is over its rating or close to it, so is
                # the load (it is part of what overloads it), not "ok"
                "power_status": (
                    node["status"]
                    if node and node["status"] in ("over", "warn")
                    else power.get("status", "ok" if r.power_node_id is None else "unpowered")
                ),
            }
        )
    return {
        "points": weights,
        "nodes": list(evaluation.nodes.values()),
        "loads": loads,
        "errors": evaluation.errors,
        "unassigned_weight": [r.label for r in rows if r.weight_kg and not r.rigging_point_id],
        "unassigned_power": [r.label for r in rows if r.power_w and not r.power_node_id],
    }


async def _venue_power_links(
    db: AsyncSession, job_id: UUID | None, venue_id: UUID | None = None
) -> tuple[dict, dict]:
    """Attribute each job/venue load's watts to the venue outlet/group it ultimately draws from.

    A device hangs on a power node; walking up the node chain finds the first node that represents a
    venue supply element (it carries ``venue_outlet_id`` / ``venue_group_id``). That is where the
    device's draw counts against the venue's own breakers, so an overloaded device trips every
    venue panel above it just as it would on site.
    """
    rows = await service.collect_loads(db, job_id, venue_id)
    nodes = await service.list_nodes(db, job_id, venue_id)
    feeds = await service.list_feeds(db, job_id, venue_id)
    node_by_id = {str(n.id): n for n in nodes}
    parents: dict[str, list[str]] = defaultdict(list)
    for feed in feeds:
        parents[str(feed.node_id)].append(str(feed.parent_id))

    outlet_watts: dict[UUID, float] = defaultdict(float)
    group_direct_watts: dict[UUID, float] = defaultdict(float)

    def supply_of(node_id: str | None) -> tuple[str, UUID] | None:
        seen: set[str] = set()
        current = node_id
        while current and current not in seen:
            seen.add(current)
            node = node_by_id.get(current)
            if node is None:
                return None
            if node.venue_outlet_id:
                return ("outlet", node.venue_outlet_id)
            if node.venue_group_id:
                return ("group", node.venue_group_id)
            current = parents.get(current, [None])[0]
        return None

    for row in rows:
        watts = row.power_w or 0.0
        if not watts:
            continue
        supply = supply_of(str(row.power_node_id) if row.power_node_id else None)
        if supply is None:
            continue
        if supply[0] == "outlet":
            outlet_watts[supply[1]] += watts
        else:
            group_direct_watts[supply[1]] += watts
    return dict(outlet_watts), dict(group_direct_watts)


@router.get("/jobs/{job_id}/power-load", response_model=venue_schemas.VenuePowerLoadRead)
async def job_venue_power_load(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> venue_schemas.VenuePowerLoadRead:
    """Device-driven load for the job's venue supply, used by the over-limit check.

    Reuses the venue supply summary but feeds it the job's actual device watts (each attributed to
    the venue outlet/group it draws from) instead of the venue template's own base-rig devices.
    """
    job = await _job(db, job_id)
    if not job.venue_id:
        return venue_schemas.VenuePowerLoadRead()
    groups = (
        await db.scalars(select(VenuePowerGroup).where(VenuePowerGroup.venue_id == job.venue_id))
    ).all()
    outlets = (
        await db.scalars(select(VenuePowerOutlet).where(VenuePowerOutlet.venue_id == job.venue_id))
    ).all()
    outlet_watts, group_direct_watts = await _venue_power_links(db, job_id)
    summary = summarize_venue_power(groups, outlets, outlet_watts, group_direct_watts)
    return venue_schemas.VenuePowerLoadRead(
        outlets=[venue_schemas.VenuePowerElementLoad(**vars(e)) for e in summary.outlets],
        groups=[venue_schemas.VenuePowerElementLoad(**vars(e)) for e in summary.groups],
        supplies=[venue_schemas.VenuePowerElementLoad(**vars(e)) for e in summary.supplies],
        total_watts=summary.total_watts,
        total_amps=summary.total_amps,
    )


@router.patch("/jobs/{job_id}/rigging/loads/{kind}/{load_id}", status_code=204)
async def assign_load(
    job_id: UUID | None = None,
    kind: str = "",
    load_id: UUID | None = None,
    payload: schemas.LoadAssign = None,
    venue_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Assign a load (fixture/element/device) to a rigging point and/or power node.

    Shared by the graph-native ``PUT /loads/{node_id}`` route (job and venue); the legacy table path
    is invoked with ``job_id`` only. Venues skip the legacy rows entirely.
    """
    await _scope(db, job_id, venue_id)
    if kind not in ("fixture", "element", "device"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown load kind")
    rows = await service.collect_loads(db, job_id, venue_id)
    row = next((r for r in rows if r.id == str(load_id) and r.kind == kind), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("rigging_point_id") is not None:
        await _found(
            await service.get_point(db, job_id, data["rigging_point_id"], venue_id),
            "Rigging point not found for this job",
        )
    if data.get("power_node_id") is not None:
        await _found(
            await service.get_node(db, job_id, data["power_node_id"], venue_id),
            "Power node not found",
        )
    connector = data.get("power_connector")
    if connector is not None and connector and not connectors.known(connector):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown connector {connector}")

    if "power_node_id" in data:
        node_id = str(data["power_node_id"]) if data["power_node_id"] else None
    else:
        node_id = row.power_node_id
    if "power_connector" in data:
        new_connector = data["power_connector"] or ""
    else:
        new_connector = row.power_connector
    if node_id is None:
        new_connector = ""
    updated = dc_replace(row, power_node_id=node_id, power_connector=new_connector)
    other = [r for r in rows if r.id != row.id]
    nodes = await service.list_nodes(db, job_id, venue_id)
    feeds = await service.list_feeds(db, job_id, venue_id)
    tree_rows = service.to_tree_loads(other + [updated])
    evaluation = power_tree.evaluate(service.to_tree_nodes(nodes, feeds), tree_rows)
    target_name = ""
    if node_id:
        target_name = next((n.name for n in nodes if str(n.id) == node_id), "")
    await _reject(_problems(evaluation, row.label, target_name))

    if kind == "fixture":
        if await lighting_service.get_fixture(db, job_id, load_id, venue_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
        # fixtures live on the graph: their load links are set by the fixture store
        changes = {k: v for k, v in data.items() if k in ("power_node_id", "rigging_point_id")}
        if "power_connector" in data:
            changes["power_connector"] = data["power_connector"] or ""
        await fixtures_native.update_fixture(db, job_id, load_id, changes, venue_id)
        await db.commit()
        return
    elif kind == "element":
        # plot elements live on the graph: their load links are set by the element store
        changes = {k: v for k, v in data.items() if k in ("power_node_id", "rigging_point_id")}
        if "power_connector" in data:
            changes["power_connector"] = data["power_connector"] or ""
        await plot_native.update_element(db, job_id, load_id, changes, venue_id)
        await db.commit()
        return
    else:
        device = await audio_service.get_device(db, load_id, venue_id=venue_id)
        if device is None or not belongs_to(device, job_id, venue_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
        # devices live on the graph: their load links are set by the device store
        changes = {k: v for k, v in data.items() if k in ("power_node_id", "rigging_point_id")}
        if "power_connector" in data:
            changes["power_connector"] = data["power_connector"] or ""
        await devices_native.update_device(db, load_id, changes, job_id, venue_id)
        await db.commit()
