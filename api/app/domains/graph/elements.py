"""Plot element links (channel, device, patch point, video input, power node, ...).

An element's link edges are derived from its link attributes (``plot_native``), so a link is set
by writing the attribute. The ids are the public ids the plot already holds (a link edge carries
them as ``legacy_target``); the graph is synced straight after so the link edges follow.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.auth.deps import get_current_user
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import audio_native, devices_native, plot_native, power_native, schemas
from app.domains.graph.backfill import backfill_job, job_lock
from app.domains.graph.ids import public_id
from app.domains.graph.models import GraphDevice

router = APIRouter(
    prefix="/jobs/{job_id}/graph",
    tags=["graph:elements"],
    dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)],
)


class ElementLinks(BaseModel):
    linked_channel_id: UUID | None = None
    linked_device_id: UUID | None = None
    linked_patch_point_id: UUID | None = None
    linked_output_point_id: UUID | None = None
    linked_video_input_id: UUID | None = None
    linked_lens_device_id: UUID | None = None
    power_node_id: UUID | None = None
    rigging_point_id: UUID | None = None


async def _owned_by_job(db: AsyncSession, column: str, job_id: UUID, value: UUID) -> bool:
    """Whether the id in a link column belongs to the job (the tables and nodes it lives on)."""
    if column in ("linked_device_id", "linked_lens_device_id"):
        return await devices_native.node_of(db, value, job_id) is not None
    targets = await audio_native.plot_targets(db, job_id)
    if column == "linked_channel_id":
        return value in targets["channels"]
    if column == "linked_patch_point_id":
        return value in targets["patch_point_device"]
    if column == "linked_output_point_id":
        return value in targets["output_point_device"]
    raise ValueError(column)


@router.put("/plot-elements/{node_id}/links", response_model=schemas.GraphDeviceRead)
async def set_element_links(
    job_id: UUID, node_id: UUID, payload: ElementLinks, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Set or clear the links of a plot element; only the keys sent change."""
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id or not plot_native.is_element(node):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plot element not found")
    data = payload.model_dump(exclude_unset=True)
    for column, value in data.items():
        if value is None:
            continue
        if column == "power_node_id":
            # power nodes are graph nodes; the link holds the power node's public id
            owned = await power_native.get_node(db, job_id, value) is not None
        elif column == "rigging_point_id":
            # rigging points are graph nodes; the link holds the node's public id
            points = await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.kind == "rigging_point"
                )
            )
            owned = any(public_id(n) == value for n in points.all())
        elif column == "linked_video_input_id":
            # video inputs are graph nodes; the link holds the node's public id
            inputs = await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.kind == "video_input"
                )
            )
            owned = any(public_id(n) == value for n in inputs.all())
        else:
            owned = await _owned_by_job(db, column, job_id, value)
        if not owned:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{column} does not belong to this job"
            )
    async with job_lock(job_id):
        await plot_native.update_element(db, job_id, public_id(node), data)
        await db.commit()
    db.expire_all()
    await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(await db.get(GraphDevice, node_id))
