from collections import defaultdict
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
from app.domains.venues.power_load import summarize_venue_power


def _uuid(value) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return None


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
    # Outlets are connected to a circuit (kind='group'), never directly to a panel.
    if group.kind != "group":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Outlets must be connected to a circuit (group), not a panel",
        )


async def _validate_supply_topology(
    db: AsyncSession, venue_id: UUID, kind: str, parent_id: UUID | None
) -> None:
    """Enforce how the supply tree may be wired.

    incoming: the mains, no parent. panel: a board hung off the incoming supply or another panel.
    group: a fused circuit that must live inside a panel. Matches ``kind`` on ``VenuePowerGroup``.
    """
    if kind == "incoming" and parent_id is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The incoming supply cannot have a parent",
        )
    if parent_id is None:
        # A top-level panel or a single circuit without a named panel are both allowed (a small
        # venue may feed circuits straight from the incoming supply); the UI steers toward panels.
        return
    parent = await db.get(VenuePowerGroup, parent_id)
    if parent is None or parent.venue_id != venue_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Parent power group not found")
    if kind == "panel" and parent.kind not in ("incoming", "panel"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A panel can only hang off the incoming supply or another panel",
        )
    if kind == "group" and parent.kind != "panel":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A circuit (group) must belong to a panel",
        )


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
    await _validate_supply_topology(db, venue_id, payload.kind, payload.parent_id)
    group = VenuePowerGroup(venue_id=venue_id, **payload.model_dump())
    # is_incoming mirrors kind=='incoming' so it stays a reliable "is this the supply root?" flag.
    group.is_incoming = payload.kind == "incoming"
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
    data = payload.model_dump(exclude_unset=True)
    # Effective kind/parent after this edit, used for both the cycle and topology checks.
    new_kind = data.get("kind", group.kind)
    new_parent = data.get("parent_id", group.parent_id)
    # A group cannot be nested under itself or under one of its own descendants, otherwise the
    # recursive load sum would loop. Walk up from the proposed parent and stop at a cycle.
    if new_parent is not None:
        if new_parent == group_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A power group cannot be its own parent"
            )
        ancestor = await db.get(VenuePowerGroup, new_parent)
        while ancestor is not None:
            if ancestor.id == group_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "A power group cannot be nested under one of its own descendants",
                )
            ancestor = (
                await db.get(VenuePowerGroup, ancestor.parent_id) if ancestor.parent_id else None
            )
    await _validate_supply_topology(db, venue_id, new_kind, new_parent)
    for key, value in data.items():
        setattr(group, key, value)
    # Keep is_incoming mirroring kind so the supply root stays unambiguous.
    group.is_incoming = group.kind == "incoming"
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
    # child panels are detached (they become top-level) rather than deleted with the parent
    for sub in await db.scalars(
        select(VenuePowerGroup).where(VenuePowerGroup.parent_id == group_id)
    ):
        sub.parent_id = None
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


@router.get("/venues/{venue_id}/power-load", response_model=schemas.VenuePowerLoadRead)
async def venue_power_load(
    venue_id: UUID, db: AsyncSession = Depends(get_db)
) -> schemas.VenuePowerLoadRead:
    """Device-driven load for the venue's supply, used by the over-limit check.

    The load is the watts of the venue's Standard Base Rig devices, each attributed to the outlet
    or group it plugs into (``attributes.venue_outlet_id`` / ``attributes.venue_group_id`` on the
    device). This is the actual draw, not the sum of each socket's capacity, so a panel with
    several sockets is not marked overloaded just for existing.
    """
    await _get_venue_or_404(db, venue_id)
    devices = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.venue_id == venue_id, GraphDevice.job_id.is_(None)
            )
        )
    ).all()
    outlet_watts: dict[UUID, float] = defaultdict(float)
    group_direct_watts: dict[UUID, float] = defaultdict(float)
    for device in devices:
        attrs = device.attributes or {}
        raw = attrs.get("power_w")
        if raw is None:
            continue
        try:
            watts = float(raw)
        except (TypeError, ValueError):
            continue
        outlet_id = _uuid(attrs.get("venue_outlet_id"))
        group_id = _uuid(attrs.get("venue_group_id"))
        if outlet_id is not None:
            outlet_watts[outlet_id] += watts
        elif group_id is not None:
            group_direct_watts[group_id] += watts

    groups = (
        await db.scalars(select(VenuePowerGroup).where(VenuePowerGroup.venue_id == venue_id))
    ).all()
    outlets = (
        await db.scalars(select(VenuePowerOutlet).where(VenuePowerOutlet.venue_id == venue_id))
    ).all()
    summary = summarize_venue_power(groups, outlets, dict(outlet_watts), dict(group_direct_watts))
    return schemas.VenuePowerLoadRead(
        outlets=[schemas.VenuePowerElementLoad(**vars(e)) for e in summary.outlets],
        groups=[schemas.VenuePowerElementLoad(**vars(e)) for e in summary.groups],
        incoming=(
            schemas.VenuePowerElementLoad(**vars(summary.incoming)) if summary.incoming else None
        ),
        total_watts=summary.total_watts,
        total_amps=summary.total_amps,
    )


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
