from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import ProductionJob
from app.domains.venues.models import Venue

SNAPSHOT_FIELDS = (
    "venue_width_cm",
    "venue_height_cm",
    "stage_x_cm",
    "stage_y_cm",
    "stage_width_cm",
    "stage_height_cm",
)


async def list_venues(db: AsyncSession) -> list[Venue]:
    result = await db.execute(select(Venue).order_by(Venue.name))
    return list(result.scalars().all())


async def get_venue(db: AsyncSession, venue_id: UUID) -> Venue | None:
    return await db.get(Venue, venue_id)


async def create_venue(db: AsyncSession, data: dict) -> Venue:
    venue = Venue(**data)
    db.add(venue)
    await db.commit()
    await db.refresh(venue)
    return venue


async def update_venue(db: AsyncSession, venue: Venue, data: dict) -> Venue:
    for key, value in data.items():
        setattr(venue, key, value)
    await db.commit()
    await db.refresh(venue)
    return venue


async def delete_venue(db: AsyncSession, venue: Venue) -> None:
    await db.execute(
        update(ProductionJob).where(ProductionJob.venue_id == venue.id).values(venue_id=None)
    )
    await db.delete(venue)
    await db.commit()


def _apply_venue_snapshot(job: ProductionJob, venue: Venue) -> None:
    for field in SNAPSHOT_FIELDS:
        setattr(job, field, getattr(venue, field))
    job.venue_background_image_url = venue.background_image_url
    job.audience_polygon = list(venue.audience_polygon or [])
    job.venue_name = venue.name


async def assign_venue(db: AsyncSession, job: ProductionJob, venue: Venue | None) -> ProductionJob:
    job.venue_id = venue.id if venue else None
    if venue is not None:
        _apply_venue_snapshot(job, venue)
    await db.commit()
    await db.refresh(job)
    return job


async def propagate_venue(db: AsyncSession, venue: Venue, scope: str) -> list[ProductionJob]:
    """Copy the venue's current dimensions into the jobs that use it.

    scope="all" updates every job assigned to the venue. scope="newer" only updates
    jobs created since the venue was last propagated (or since the venue was created,
    if it has never been propagated).
    """
    query = select(ProductionJob).where(ProductionJob.venue_id == venue.id)
    if scope == "newer":
        cutoff = venue.propagated_at or venue.created_at
        query = query.where(ProductionJob.created_at > cutoff)
    result = await db.execute(query)
    jobs = list(result.scalars().all())
    for job in jobs:
        _apply_venue_snapshot(job, venue)
    venue.propagated_at = datetime.now()
    await db.commit()
    for job in jobs:
        await db.refresh(job)
    return jobs
