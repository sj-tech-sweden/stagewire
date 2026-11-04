from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import schemas as audio_schemas
from app.domains.audio import service as audio_service
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph.models import GraphDevice
from app.domains.graph.schemas import GraphRead
from app.domains.rigging import connectors
from app.domains.venues import schemas, service
from app.domains.venues.base_rig import get_base_rig, replace_base_rig
from app.domains.venues.models import VenuePowerGroup, VenuePowerOutlet

router = APIRouter(
    tags=["venues"], dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)]
)


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


async def _check_group(db: AsyncSession, venue_id: UUID, group_id: UUID | None) -> None:
    if group_id is None:
        return
    group = await db.get(VenuePowerGroup, group_id)
    if group is None or group.venue_id != venue_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Power group not found")


@router.get("/venues/{venue_id}/power-groups", response_model=list[schemas.VenuePowerGroupRead])
async def list_power_groups(venue_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_venue_or_404(db, venue_id)
    result = await db.execute(
        select(VenuePowerGroup)
        .where(VenuePowerGroup.venue_id == venue_id)
        .order_by(VenuePowerGroup.name)
    )
    return list(result.scalars().all())


@router.post(
    "/venues/{venue_id}/power-groups",
    response_model=schemas.VenuePowerGroupRead,
    status_code=201,
)
async def create_power_group(
    venue_id: UUID, payload: schemas.VenuePowerGroupCreate, db: AsyncSession = Depends(get_db)
):
    await _get_venue_or_404(db, venue_id)
    group = VenuePowerGroup(venue_id=venue_id, **payload.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.patch(
    "/venues/{venue_id}/power-groups/{group_id}", response_model=schemas.VenuePowerGroupRead
)
async def update_power_group(
    venue_id: UUID,
    group_id: UUID,
    payload: schemas.VenuePowerGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _get_venue_or_404(db, venue_id)
    group = await db.get(VenuePowerGroup, group_id)
    if group is None or group.venue_id != venue_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Power group not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/venues/{venue_id}/power-groups/{group_id}", status_code=204)
async def delete_power_group(
    venue_id: UUID, group_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await _get_venue_or_404(db, venue_id)
    group = await db.get(VenuePowerGroup, group_id)
    if group is None or group.venue_id != venue_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Power group not found")
    for outlet in await db.scalars(
        select(VenuePowerOutlet).where(VenuePowerOutlet.group_id == group_id)
    ):
        outlet.group_id = None
    # power nodes made from the group (on the graph) forget it
    for node in await db.scalars(
        select(GraphDevice).where(
            GraphDevice.attributes["venue_group_id"].as_string() == str(group_id)
        )
    ):
        node.attributes = {k: v for k, v in node.attributes.items() if k != "venue_group_id"}
    await db.delete(group)
    await db.commit()


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
    await _check_group(db, venue_id, payload.group_id)
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
    if "group_id" in data:
        await _check_group(db, venue_id, data["group_id"])
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


# --- Standard Base Rig -------------------------------------------------------------------------


@router.get("/venues/{venue_id}/graph", response_model=GraphRead)
async def get_venue_base_rig(venue_id: UUID, db: AsyncSession = Depends(get_db)) -> GraphRead:
    """The venue's Standard Base Rig: the graph of devices/edges it seeds jobs with."""
    await _get_venue_or_404(db, venue_id)
    return await get_base_rig(db, venue_id)


@router.put("/venues/{venue_id}/graph", response_model=GraphRead)
async def put_venue_base_rig(
    venue_id: UUID, payload: schemas.VenueBaseRigWrite, db: AsyncSession = Depends(get_db)
) -> GraphRead:
    """Replace the venue's entire Standard Base Rig.

    The editor holds the full graph locally and PUTs it back in one shot, keeping device/edge ids
    stable so no remapping is required. This is the venue counterpart to a job's incremental graph
    edits and intentionally skips the job-only mirroring machinery.
    """
    await _get_venue_or_404(db, venue_id)
    return await replace_base_rig(db, venue_id, payload)
