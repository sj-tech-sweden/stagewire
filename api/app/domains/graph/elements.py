"""Plot element links (channel, device, patch point, video input, power node, ...).

An element's link edges are derived from its legacy link columns, so a link is set by writing the
column. The ids are the legacy ids the plot already holds (a link edge carries them as
``legacy_target``); the graph is synced straight after so the link edges follow.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelListOutput,
    ChannelPatchPoint,
    OutputPatchPoint,
    StagePlotElement,
)
from app.domains.auth.deps import get_current_user
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import power_native, schemas
from app.domains.graph.backfill import backfill_job, job_lock
from app.domains.graph.ids import public_id
from app.domains.graph.lists import _by_ref
from app.domains.graph.mirror import legacy_target
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


def _owned_by_job(column: str, job_id: UUID, value: UUID):
    if column in ("linked_device_id", "linked_lens_device_id"):
        return select(AudioDevice.id).where(AudioDevice.id == value, AudioDevice.job_id == job_id)
    if column == "linked_channel_id":
        return (
            select(AudioChannelPatch.id)
            .join(ChannelList, AudioChannelPatch.channel_list_id == ChannelList.id)
            .where(AudioChannelPatch.id == value, ChannelList.job_id == job_id)
        )
    if column == "linked_patch_point_id":
        return (
            select(ChannelPatchPoint.id)
            .join(AudioChannelPatch, ChannelPatchPoint.channel_id == AudioChannelPatch.id)
            .join(ChannelList, AudioChannelPatch.channel_list_id == ChannelList.id)
            .where(ChannelPatchPoint.id == value, ChannelList.job_id == job_id)
        )
    if column == "linked_output_point_id":
        return (
            select(OutputPatchPoint.id)
            .join(ChannelListOutput, OutputPatchPoint.output_id == ChannelListOutput.id)
            .join(ChannelList, ChannelListOutput.channel_list_id == ChannelList.id)
            .where(OutputPatchPoint.id == value, ChannelList.job_id == job_id)
        )
    raise ValueError(column)


@router.put("/plot-elements/{node_id}/links", response_model=schemas.GraphDeviceRead)
async def set_element_links(
    job_id: UUID, node_id: UUID, payload: ElementLinks, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Set or clear the links of a plot element; only the keys sent change."""
    node = await db.get(GraphDevice, node_id)
    target = legacy_target(node) if node is not None else None
    if (
        node is None
        or node.job_id != job_id
        or target is None
        or target[0] != "stage_plot_elements"
    ):
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
            owned = await db.scalar(_owned_by_job(column, job_id, value)) is not None
        if not owned:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{column} does not belong to this job"
            )
    async with job_lock(job_id):
        element = await db.get(StagePlotElement, target[1])
        if element is None or element.job_id != job_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Plot element not found")
        for column, value in data.items():
            setattr(element, column, value)
        await db.commit()
    db.expire_all()
    await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(
        await _by_ref(db, job_id, f"stage_plot_elements:{target[1]}")
    )
