from dataclasses import replace as dc_replace
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.audio.models import StagePlotElement
from app.domains.auth.deps import get_current_user
from app.domains.lighting.models import LightingFixture
from app.domains.rigging import calc, connectors, power_tree, schemas, service
from app.domains.rigging.models import PowerNode, RiggingPoint
from app.domains.venues.schemas import VenuePowerOutletRead

router = APIRouter(tags=["rigging"], dependencies=[Depends(get_current_user)])


async def _job(db: AsyncSession, job_id: UUID):
    job = await audio_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    return job


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


async def _check_device(db: AsyncSession, job_id: UUID, device_id: UUID | None) -> None:
    if device_id is None:
        return
    device = await audio_service.get_device(db, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")


def _problems(evaluation: power_tree.Evaluation, *names: str) -> list[str]:
    """Errors that mention one of the given names (the node or load being changed)."""
    return [e for e in evaluation.errors if any(n and n in e for n in names)]


async def _reject(problems: list[str]) -> None:
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))


@router.get("/power-connectors")
async def list_connectors() -> list[dict]:
    return connectors.catalog()


@router.get("/jobs/{job_id}/power-outlets", response_model=list[VenuePowerOutletRead])
async def list_job_outlets(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await _job(db, job_id)
    return await service.venue_outlets(db, job.venue_id)


@router.get("/jobs/{job_id}/rigging-points", response_model=list[schemas.RiggingPointRead])
async def list_points(job_id: UUID, db: AsyncSession = Depends(get_db)):
    await _job(db, job_id)
    return await service.list_points(db, job_id)


@router.post(
    "/jobs/{job_id}/rigging-points",
    response_model=schemas.RiggingPointRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_point(
    job_id: UUID, payload: schemas.RiggingPointCreate, db: AsyncSession = Depends(get_db)
):
    await _job(db, job_id)
    position = await service.next_position(db, RiggingPoint, job_id)
    return await service.save(
        db, RiggingPoint(job_id=job_id, position=position, **payload.model_dump())
    )


@router.patch("/jobs/{job_id}/rigging-points/{point_id}", response_model=schemas.RiggingPointRead)
async def update_point(
    job_id: UUID,
    point_id: UUID,
    payload: schemas.RiggingPointUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _job(db, job_id)
    point = await _found(await service.get_point(db, job_id, point_id), "Rigging point not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(point, key, value)
    return await service.save(db, point)


@router.delete("/jobs/{job_id}/rigging-points/{point_id}", status_code=204)
async def delete_point(job_id: UUID, point_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await _job(db, job_id)
    point = await _found(await service.get_point(db, job_id, point_id), "Rigging point not found")
    await db.delete(point)
    await db.commit()


@router.get("/jobs/{job_id}/power-nodes")
async def list_nodes(job_id: UUID, db: AsyncSession = Depends(get_db)) -> list[dict]:
    await _job(db, job_id)
    nodes = await service.list_nodes(db, job_id)
    return [schemas.PowerNodeRead.model_validate(n).model_dump(mode="json") for n in nodes]


@router.post(
    "/jobs/{job_id}/power-nodes",
    response_model=schemas.PowerNodeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_node(
    job_id: UUID, payload: schemas.PowerNodeCreate, db: AsyncSession = Depends(get_db)
):
    job = await _job(db, job_id)
    data = payload.model_dump(exclude_unset=True)
    outputs = _outputs(payload.outputs)
    _check_connectors(outputs, payload.feed_connector, payload.rating_amps)
    await _check_device(db, job_id, payload.device_id)
    if payload.kind == "source":
        if payload.parent_id is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A source has no parent")
    elif payload.parent_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Connect it to a parent node")
    if payload.venue_outlet_id is not None:
        outlet = await _found(
            await service.get_outlet(db, job.venue_id, payload.venue_outlet_id),
            "Venue outlet not found for this job",
        )
        if outlet.connector != payload.feed_connector:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"The outlet is {outlet.connector}; the node is fed by {payload.feed_connector}",
            )
    nodes = await service.list_nodes(db, job_id)
    rows = await service.collect_loads(db, job_id)
    candidate = PowerNode(
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
    tree = service.to_tree_nodes(nodes + [candidate])
    evaluation = power_tree.evaluate(tree, service.to_tree_loads(rows))
    await _reject(_problems(evaluation, candidate.name))
    position = await service.next_position(db, PowerNode, job_id)
    node = PowerNode(
        job_id=job_id, position=position, **{k: v for k, v in data.items() if k != "outputs"}
    )
    node.outputs = outputs
    return await service.save(db, node)


@router.patch("/jobs/{job_id}/power-nodes/{node_id}", response_model=schemas.PowerNodeRead)
async def update_node(
    job_id: UUID,
    node_id: UUID,
    payload: schemas.PowerNodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    job = await _job(db, job_id)
    node = await _found(await service.get_node(db, job_id, node_id), "Power node not found")
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
    await _check_device(db, job_id, data.get("device_id"))
    if data.get("venue_outlet_id") is not None:
        await _found(
            await service.get_outlet(db, job.venue_id, data["venue_outlet_id"]),
            "Venue outlet not found for this job",
        )
    nodes = await service.list_nodes(db, job_id)
    rows = await service.collect_loads(db, job_id)
    tree = service.to_tree_nodes(nodes)
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
            nodes, str(node.id)
        ) | {str(node.id)}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A node cannot hang from itself"
            )
        changed["parent_id"] = str(changed["parent_id"]) if changed["parent_id"] else None
    tree = [dc_replace(n, **changed) if n.id == str(node.id) else n for n in tree]
    if "name" in changed:
        names = (changed["name"], node.name)
    else:
        names = (node.name,)
    evaluation = power_tree.evaluate(tree, service.to_tree_loads(rows))
    await _reject(_problems(evaluation, *names))
    for key, value in data.items():
        setattr(node, key, value)
    return await service.save(db, node)


def _descendant_ids(nodes: list[PowerNode], node_id: str) -> set[str]:
    children: dict[str, list[str]] = {}
    for n in nodes:
        if n.parent_id:
            children.setdefault(str(n.parent_id), []).append(str(n.id))
    found: set[str] = set()
    stack = [node_id]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


@router.delete("/jobs/{job_id}/power-nodes/{node_id}", status_code=204)
async def delete_node(job_id: UUID, node_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await _job(db, job_id)
    node = await _found(await service.get_node(db, job_id, node_id), "Power node not found")
    nodes = await service.list_nodes(db, job_id)
    if any(n.parent_id == node.id for n in nodes):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Move or remove the nodes fed from this one first"
        )
    rows = await service.collect_loads(db, job_id)
    if any(r.power_node_id == str(node.id) for r in rows):
        raise HTTPException(status.HTTP_409_CONFLICT, "Unplug the loads on this node first")
    await db.delete(node)
    await db.commit()


@router.get("/jobs/{job_id}/rigging/loads", response_model=list[schemas.LoadRead])
async def list_loads(job_id: UUID, db: AsyncSession = Depends(get_db)):
    await _job(db, job_id)
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
        for r in await service.collect_loads(db, job_id)
    ]


@router.get("/jobs/{job_id}/rigging/summary")
async def rigging_summary(job_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    await _job(db, job_id)
    points = [
        {"id": str(p.id), "name": p.name, "weight_capacity_kg": p.weight_capacity_kg}
        for p in await service.list_points(db, job_id)
    ]
    rows = await service.collect_loads(db, job_id)
    evaluation = power_tree.evaluate(
        service.to_tree_nodes(await service.list_nodes(db, job_id)), service.to_tree_loads(rows)
    )
    loads = []
    for r in rows:
        power = evaluation.loads.get(r.id, {})
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
                "power_status": power.get(
                    "status", "ok" if r.power_node_id is None else "unpowered"
                ),
            }
        )
    return {
        "points": calc.summarize_weights(points, service.weight_loads(rows)),
        "nodes": list(evaluation.nodes.values()),
        "loads": loads,
        "errors": evaluation.errors,
        "unassigned_weight": [r.label for r in rows if r.weight_kg and not r.rigging_point_id],
        "unassigned_power": [r.label for r in rows if r.power_w and not r.power_node_id],
    }


@router.patch("/jobs/{job_id}/rigging/loads/{kind}/{load_id}", status_code=204)
async def assign_load(
    job_id: UUID,
    kind: str,
    load_id: UUID,
    payload: schemas.LoadAssign,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _job(db, job_id)
    if kind not in ("fixture", "element"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown load kind")
    rows = await service.collect_loads(db, job_id)
    row = next((r for r in rows if r.id == str(load_id) and r.kind == kind), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("rigging_point_id") is not None:
        await _found(
            await service.get_point(db, job_id, data["rigging_point_id"]),
            "Rigging point not found for this job",
        )
    if data.get("power_node_id") is not None:
        await _found(
            await service.get_node(db, job_id, data["power_node_id"]), "Power node not found"
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
    nodes = await service.list_nodes(db, job_id)
    tree_rows = service.to_tree_loads(other + [updated])
    evaluation = power_tree.evaluate(service.to_tree_nodes(nodes), tree_rows)
    target_name = ""
    if node_id:
        target_name = next((n.name for n in nodes if str(n.id) == node_id), "")
    await _reject(_problems(evaluation, row.label, target_name))

    if kind == "fixture":
        fixture = await db.get(LightingFixture, load_id)
        if fixture is None or fixture.job_id != job_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
        target = fixture
    else:
        element = await db.get(StagePlotElement, load_id)
        if element is None or element.job_id != job_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Load not found")
        target = element
    for key, value in data.items():
        if key == "power_node_id":
            target.power_node_id = value
        elif key == "rigging_point_id":
            target.rigging_point_id = value
        elif key == "power_connector":
            target.power_connector = value or ""
    if target.power_node_id is None:
        target.power_connector = ""
    await db.commit()
