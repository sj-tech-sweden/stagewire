from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.rigging import calc, schemas, service
from app.domains.rigging.models import PowerCircuit, PowerDistro, RiggingPoint

router = APIRouter(tags=["rigging"], dependencies=[Depends(get_current_user)])


async def _job_or_404(db: AsyncSession, job_id: UUID) -> None:
    if await audio_service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")


async def _found(obj, detail: str):
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    return obj


def _dump(obj) -> dict:
    return {
        column.name: getattr(obj, column.name)
        for column in obj.__table__.columns
        if column.name != "job_id"
    }


@router.get("/jobs/{job_id}/rigging-points", response_model=list[schemas.RiggingPointRead])
async def list_points(job_id: UUID, db: AsyncSession = Depends(get_db)):
    await _job_or_404(db, job_id)
    return await service.list_points(db, job_id)


@router.post(
    "/jobs/{job_id}/rigging-points",
    response_model=schemas.RiggingPointRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_point(
    job_id: UUID, payload: schemas.RiggingPointCreate, db: AsyncSession = Depends(get_db)
):
    await _job_or_404(db, job_id)
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
    await _job_or_404(db, job_id)
    point = await _found(await service.get_point(db, job_id, point_id), "Rigging point not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(point, key, value)
    return await service.save(db, point)


@router.delete("/jobs/{job_id}/rigging-points/{point_id}", status_code=204)
async def delete_point(job_id: UUID, point_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await _job_or_404(db, job_id)
    point = await _found(await service.get_point(db, job_id, point_id), "Rigging point not found")
    await db.delete(point)
    await db.commit()


@router.get("/jobs/{job_id}/power-distros", response_model=list[schemas.PowerDistroRead])
async def list_distros(job_id: UUID, db: AsyncSession = Depends(get_db)):
    await _job_or_404(db, job_id)
    return await service.list_distros(db, job_id)


@router.post(
    "/jobs/{job_id}/power-distros",
    response_model=schemas.PowerDistroRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_distro(
    job_id: UUID, payload: schemas.PowerDistroCreate, db: AsyncSession = Depends(get_db)
):
    await _job_or_404(db, job_id)
    position = await service.next_position(db, PowerDistro, job_id)
    return await service.save(
        db, PowerDistro(job_id=job_id, position=position, **payload.model_dump())
    )


@router.patch("/jobs/{job_id}/power-distros/{distro_id}", response_model=schemas.PowerDistroRead)
async def update_distro(
    job_id: UUID,
    distro_id: UUID,
    payload: schemas.PowerDistroUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _job_or_404(db, job_id)
    distro = await _found(await service.get_distro(db, job_id, distro_id), "Distro not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(distro, key, value)
    return await service.save(db, distro)


@router.delete("/jobs/{job_id}/power-distros/{distro_id}", status_code=204)
async def delete_distro(job_id: UUID, distro_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await _job_or_404(db, job_id)
    distro = await _found(await service.get_distro(db, job_id, distro_id), "Distro not found")
    await db.delete(distro)
    await db.commit()


@router.post(
    "/jobs/{job_id}/power-circuits",
    response_model=schemas.PowerCircuitRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_circuit(
    job_id: UUID, payload: schemas.PowerCircuitCreate, db: AsyncSession = Depends(get_db)
):
    await _job_or_404(db, job_id)
    await _found(await service.get_distro(db, job_id, payload.distro_id), "Distro not found")
    position = await service.next_position(db, PowerCircuit, job_id)
    data = payload.model_dump()
    return await service.save(db, PowerCircuit(position=position, **data))


@router.patch("/jobs/{job_id}/power-circuits/{circuit_id}", response_model=schemas.PowerCircuitRead)
async def update_circuit(
    job_id: UUID,
    circuit_id: UUID,
    payload: schemas.PowerCircuitUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _job_or_404(db, job_id)
    circuit = await _found(await service.get_circuit(db, job_id, circuit_id), "Circuit not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(circuit, key, value)
    return await service.save(db, circuit)


@router.delete("/jobs/{job_id}/power-circuits/{circuit_id}", status_code=204)
async def delete_circuit(
    job_id: UUID, circuit_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await _job_or_404(db, job_id)
    circuit = await _found(await service.get_circuit(db, job_id, circuit_id), "Circuit not found")
    await db.delete(circuit)
    await db.commit()


@router.get("/jobs/{job_id}/rigging/loads", response_model=list[schemas.LoadRead])
async def list_loads(job_id: UUID, db: AsyncSession = Depends(get_db)):
    await _job_or_404(db, job_id)
    return [
        schemas.LoadRead(
            id=UUID(load.id),
            kind=load.kind,
            label=load.label,
            weight_kg=load.weight_kg,
            power_w=load.power_w,
            rigging_point_id=UUID(load.rigging_point_id) if load.rigging_point_id else None,
            power_circuit_id=UUID(load.power_circuit_id) if load.power_circuit_id else None,
        )
        for load in await service.collect_loads(db, job_id)
    ]


@router.get("/jobs/{job_id}/rigging/summary")
async def rigging_summary(job_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    await _job_or_404(db, job_id)
    points = [_dump(p) for p in await service.list_points(db, job_id)]
    distros = [_dump(d) for d in await service.list_distros(db, job_id)]
    circuits = [_dump(c) for c in await service.list_circuits(db, job_id)]
    loads = await service.collect_loads(db, job_id)
    return calc.summarize(points, distros, circuits, loads)


@router.patch("/jobs/{job_id}/rigging/loads/{kind}/{load_id}", status_code=204)
async def assign_load(
    job_id: UUID,
    kind: str,
    load_id: UUID,
    payload: schemas.LoadAssign,
    db: AsyncSession = Depends(get_db),
) -> None:
    await _job_or_404(db, job_id)
    if kind not in ("fixture", "element"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown load kind")
    data = payload.model_dump(exclude_unset=True)
    if data.get("rigging_point_id") is not None:
        await _found(
            await service.get_point(db, job_id, data["rigging_point_id"]),
            "Rigging point not found for this job",
        )
    if data.get("power_circuit_id") is not None:
        await _found(
            await service.get_circuit(db, job_id, data["power_circuit_id"]),
            "Circuit not found for this job",
        )
    try:
        await service.assign(db, job_id, kind, load_id, data)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
