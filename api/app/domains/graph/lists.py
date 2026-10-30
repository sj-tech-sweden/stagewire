"""Graph-native channel lists: lists, channels, outputs and patch chains.

The graph API is the way to author these. While the legacy tables still exist they are written
as a shadow (so unmoved readers keep working) and the graph is synced straight after.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import schemas as audio_schemas
from app.domains.audio import service
from app.domains.audio.models import ChannelPatchPoint, OutputPatchPoint
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.graph import schemas
from app.domains.graph.backfill import backfill_job
from app.domains.graph.mirror import _publish_list, legacy_target
from app.domains.graph.models import ConnectionEdge, GraphDevice

router = APIRouter(
    prefix="/jobs/{job_id}/graph", tags=["graph:lists"], dependencies=[Depends(get_current_user)]
)

MAX_BATCH = 200


class ListCreate(BaseModel):
    name: str = "Input List"
    mixer_product_id: str | None = None
    mixer_product_name: str | None = None
    mixer_inputs: int | None = None
    mixer_buses: int | None = None


class ChannelCreate(BaseModel):
    channel_number: int | None = None
    source_label: str = ""
    input_type: str | None = None
    connector: str | None = None
    device: str | None = None
    stand_type: str = ""
    instrument_group: str = "other"
    performer_name: str | None = None
    wireless_pack: str | None = None
    wireless_frequency: str | None = None
    phantom_power: bool = False
    stereo: bool = False
    stereo_channel: int | None = None
    notes: str = ""
    color_code: str | None = None
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


class OutputCreate(BaseModel):
    name: str = "Output"
    mode: str = "mono"
    connector: str | None = None
    notes: str = ""
    color_code: str | None = None


class ChainStep(BaseModel):
    device_id: UUID
    point_type: str | None = None
    connector: str = ""
    patch_label: str = ""
    notes: str = ""
    parent_index: int | None = None
    bus_connector: str | None = None
    parallel: bool = False


class Chain(BaseModel):
    steps: list[ChainStep] = Field(default_factory=list, max_length=64)


class ChainRead(BaseModel):
    edges: list[schemas.ConnectionEdgeRead]


async def _node(db: AsyncSession, job_id: UUID, node_id: UUID, kind: str) -> GraphDevice:
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id or node.kind != kind:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"{kind.replace('_', ' ').title()} not found"
        )
    return node


def _legacy_id(node: GraphDevice, table: str) -> UUID:
    target = legacy_target(node)
    if target is None or target[0] != table:
        raise HTTPException(status.HTTP_409_CONFLICT, "This node has no legacy twin to write")
    return target[1]


async def _by_ref(db: AsyncSession, job_id: UUID, ref: str) -> GraphDevice:
    node = (
        await db.scalars(
            select(GraphDevice).where(GraphDevice.job_id == job_id, GraphDevice.legacy_ref == ref)
        )
    ).first()
    if node is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Graph sync did not create it")
    return node


async def _read(db: AsyncSession, job_id: UUID, ref: str) -> schemas.GraphDeviceRead:
    await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(await _by_ref(db, job_id, ref))


async def _list_row(db: AsyncSession, job_id: UUID, list_node: GraphDevice):
    row = await service.get_channel_list(db, _legacy_id(list_node, "audio_channel_lists"))
    if row is None or row.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    return row


async def _device_twin(db: AsyncSession, job_id: UUID, node_id: UUID) -> UUID:
    """The legacy device row behind a graph device, created on demand for catalog items."""
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
    target = legacy_target(node)
    if target is not None and target[0] == "audio_devices":
        return target[1]
    if node.kind in ("channel", "output", "channel_list", "plot_element"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node is not a device")
    device = await service.create_device(
        db,
        job_id,
        {
            "name": node.name,
            "device_type": "other",
            "stockwire_product_id": node.stockwire_product_id,
            "stockwire_product_name": node.stockwire_product_name,
        },
    )
    node.legacy_ref = f"audio_devices:{device.id}"
    node.graph_edited = True
    await db.commit()
    return device.id


@router.post("/lists", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_list(
    job_id: UUID, payload: ListCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    position = len(await service.list_channel_lists(db, job_id))
    row = await service.create_channel_list(
        db, job_id, {**payload.model_dump(exclude_unset=True), "position": position}
    )
    await _publish_list(db, job_id, row.id)
    return await _read(db, job_id, f"audio_channel_lists:{row.id}")


async def _create_channels(
    db: AsyncSession, job_id: UUID, list_node_id: UUID, items: list[ChannelCreate]
) -> list[schemas.GraphDeviceRead]:
    list_node = await _node(db, job_id, list_node_id, "channel_list")
    row = await _list_row(db, job_id, list_node)
    existing = await service.list_channels(db, row.id)
    next_number = max((c.channel_number for c in existing), default=0) + 1
    created = []
    for item in items:
        data = item.model_dump(exclude_unset=True)
        if data.get("channel_number") is None:
            data["channel_number"] = next_number
        next_number = max(next_number, data["channel_number"]) + 1
        created.append(await service.create_channel(db, row.id, data))
    await backfill_job(db, job_id)
    out = []
    for channel in created:
        full = await service.get_channel(db, channel.id)
        await publish_job_event(
            job_id, "channel.upsert", audio_schemas.AudioChannelPatchRead.model_validate(full)
        )
        node = await _by_ref(db, job_id, f"audio_channel_patches:{channel.id}")
        out.append(schemas.GraphDeviceRead.model_validate(node))
    return out


@router.post("/lists/{list_id}/channels", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_channel(
    job_id: UUID, list_id: UUID, payload: ChannelCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    return (await _create_channels(db, job_id, list_id, [payload]))[0]


@router.post(
    "/lists/{list_id}/channels/batch",
    response_model=list[schemas.GraphDeviceRead],
    status_code=201,
)
async def create_channels(
    job_id: UUID, list_id: UUID, payload: list[ChannelCreate], db: AsyncSession = Depends(get_db)
) -> list[schemas.GraphDeviceRead]:
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} channels")
    return await _create_channels(db, job_id, list_id, payload)


@router.post("/lists/{list_id}/outputs", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_output(
    job_id: UUID, list_id: UUID, payload: OutputCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    list_node = await _node(db, job_id, list_id, "channel_list")
    row = await _list_row(db, job_id, list_node)
    position = len(row.outputs)
    output = await service.create_output(
        db, row.id, {**payload.model_dump(exclude_unset=True), "position": position}
    )
    await _publish_list(db, job_id, row.id)
    return await _read(db, job_id, f"channel_list_outputs:{output.id}")


async def _chain_edges(db: AsyncSession, job_id: UUID, node: GraphDevice) -> ChainRead:
    edges = (await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))).all()
    mine = [e for e in edges if (e.attributes or {}).get("chain") == str(node.id)]
    mine.sort(key=lambda e: (e.attributes or {}).get("position") or 0)
    return ChainRead(edges=[schemas.ConnectionEdgeRead.model_validate(e) for e in mine])


@router.put("/channels/{channel_id}/chain", response_model=ChainRead)
async def replace_channel_chain(
    job_id: UUID, channel_id: UUID, payload: Chain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, channel_id, "channel")
    legacy_id = _legacy_id(node, "audio_channel_patches")
    twins = [await _device_twin(db, job_id, step.device_id) for step in payload.steps]
    types = {}
    for twin in set(twins):
        device = await service.get_device(db, twin)
        types[twin] = device.device_type if device else "other"
    await db.execute(delete(ChannelPatchPoint).where(ChannelPatchPoint.channel_id == legacy_id))
    for position, (step, twin) in enumerate(zip(payload.steps, twins, strict=True)):
        db.add(
            ChannelPatchPoint(
                channel_id=legacy_id,
                position=position,
                point_type=step.point_type or types[twin],
                device_id=twin,
                connector=step.connector,
                patch_label=step.patch_label,
                notes=step.notes,
            )
        )
    await db.commit()
    await backfill_job(db, job_id)
    channel = await service.get_channel(db, legacy_id)
    await publish_job_event(
        job_id, "channel.upsert", audio_schemas.AudioChannelPatchRead.model_validate(channel)
    )
    return await _chain_edges(db, job_id, node)


@router.put("/outputs/{output_id}/chain", response_model=ChainRead)
async def replace_output_chain(
    job_id: UUID, output_id: UUID, payload: Chain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, output_id, "output")
    legacy_id = _legacy_id(node, "channel_list_outputs")
    for position, step in enumerate(payload.steps):
        if step.parent_index is not None and not 0 <= step.parent_index < position:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A step can only take its signal from an earlier step",
            )
    twins = [await _device_twin(db, job_id, step.device_id) for step in payload.steps]
    types = {}
    for twin in set(twins):
        device = await service.get_device(db, twin)
        types[twin] = device.device_type if device else "other"
    await db.execute(delete(OutputPatchPoint).where(OutputPatchPoint.output_id == legacy_id))
    created: list[OutputPatchPoint] = []
    for position, (step, twin) in enumerate(zip(payload.steps, twins, strict=True)):
        point = OutputPatchPoint(
            output_id=legacy_id,
            position=position,
            point_type=step.point_type or types[twin],
            device_id=twin,
            connector=step.connector,
            patch_label=step.patch_label,
            notes=step.notes,
            bus_connector=step.bus_connector,
            parallel=step.parallel,
            parent_id=created[step.parent_index].id if step.parent_index is not None else None,
        )
        db.add(point)
        await db.flush()
        created.append(point)
    await db.commit()
    await backfill_job(db, job_id)
    output = await service.get_output(db, legacy_id)
    await _publish_list(db, job_id, output.channel_list_id)
    return await _chain_edges(db, job_id, node)
