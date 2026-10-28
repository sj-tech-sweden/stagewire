from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import schemas as audio_schemas
from app.domains.audio import service as audio_service
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.rigging import connectors
from app.domains.venues import schemas, service
from app.domains.venues.models import VenuePowerOutlet

router = APIRouter(tags=["venues"], dependencies=[Depends(get_current_user)])


async def _get_venue_or_404(db: AsyncSession, venue_id: UUID):
    venue = await service.get_venue(db, venue_id)
    if venue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    return venue


@router.get("/venues", response_model=list[schemas.VenueRead])
async def list_venues(db: AsyncSession = Depends(get_db)) -> list[schemas.VenueRead]:
    venues = await service.list_venues(db)
    return [schemas.VenueRead.model_validate(v) for v in venues]


@router.post("/venues", response_model=schemas.VenueRead, status_code=201)
async def create_venue(
    payload: schemas.VenueCreate, db: AsyncSession = Depends(get_db)
) -> schemas.VenueRead:
    venue = await service.create_venue(db, payload.model_dump())
    return schemas.VenueRead.model_validate(venue)


@router.get("/venues/{venue_id}", response_model=schemas.VenueRead)
async def get_venue(venue_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.VenueRead:
    venue = await _get_venue_or_404(db, venue_id)
    return schemas.VenueRead.model_validate(venue)


@router.patch("/venues/{venue_id}", response_model=schemas.VenueRead)
async def update_venue(
    venue_id: UUID,
    payload: schemas.VenueUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VenueRead:
    venue = await _get_venue_or_404(db, venue_id)
    venue = await service.update_venue(db, venue, payload.model_dump(exclude_unset=True))
    return schemas.VenueRead.model_validate(venue)


@router.delete("/venues/{venue_id}", status_code=204)
async def delete_venue(venue_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    venue = await _get_venue_or_404(db, venue_id)
    await service.delete_venue(db, venue)


@router.post("/venues/{venue_id}/propagate", response_model=schemas.VenuePropagateResult)
async def propagate_venue(
    venue_id: UUID,
    payload: schemas.VenuePropagate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VenuePropagateResult:
    venue = await _get_venue_or_404(db, venue_id)
    jobs = await service.propagate_venue(db, venue, payload.scope)
    for job in jobs:
        await publish_job_event(
            job.id, "job.update", audio_schemas.ProductionJobRead.model_validate(job)
        )
    return schemas.VenuePropagateResult(updated=len(jobs))


@router.put("/jobs/{job_id}/venue", response_model=audio_schemas.ProductionJobRead)
async def assign_job_venue(
    job_id: UUID,
    payload: schemas.JobVenueAssign,
    db: AsyncSession = Depends(get_db),
) -> audio_schemas.ProductionJobRead:
    job = await audio_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    venue = None
    if payload.venue_id is not None:
        venue = await _get_venue_or_404(db, payload.venue_id)
    job = await service.assign_venue(db, job, venue)
    read = audio_schemas.ProductionJobRead.model_validate(job)
    await publish_job_event(job_id, "job.update", read)
    return read


@router.get("/venues/{venue_id}/power-outlets", response_model=list[schemas.VenuePowerOutletRead])
async def list_power_outlets(venue_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_venue_or_404(db, venue_id)
    result = await db.execute(
        select(VenuePowerOutlet)
        .where(VenuePowerOutlet.venue_id == venue_id)
        .order_by(VenuePowerOutlet.name)
    )
    return list(result.scalars().all())


@router.post(
    "/venues/{venue_id}/power-outlets",
    response_model=schemas.VenuePowerOutletRead,
    status_code=201,
)
async def create_power_outlet(
    venue_id: UUID, payload: schemas.VenuePowerOutletCreate, db: AsyncSession = Depends(get_db)
):
    await _get_venue_or_404(db, venue_id)
    if not connectors.known(payload.connector):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown connector")
    outlet = VenuePowerOutlet(venue_id=venue_id, **payload.model_dump())
    db.add(outlet)
    await db.commit()
    await db.refresh(outlet)
    return outlet


@router.patch(
    "/venues/{venue_id}/power-outlets/{outlet_id}",
    response_model=schemas.VenuePowerOutletRead,
)
async def update_power_outlet(
    venue_id: UUID,
    outlet_id: UUID,
    payload: schemas.VenuePowerOutletUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _get_venue_or_404(db, venue_id)
    outlet = await db.get(VenuePowerOutlet, outlet_id)
    if outlet is None or outlet.venue_id != venue_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outlet not found")
    data = payload.model_dump(exclude_unset=True)
    if "connector" in data and not connectors.known(data["connector"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown connector")
    for key, value in data.items():
        setattr(outlet, key, value)
    await db.commit()
    await db.refresh(outlet)
    return outlet


@router.delete("/venues/{venue_id}/power-outlets/{outlet_id}", status_code=204)
async def delete_power_outlet(
    venue_id: UUID, outlet_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await _get_venue_or_404(db, venue_id)
    outlet = await db.get(VenuePowerOutlet, outlet_id)
    if outlet is None or outlet.venue_id != venue_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outlet not found")
    await db.delete(outlet)
    await db.commit()
