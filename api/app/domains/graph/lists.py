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
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import schemas
from app.domains.graph.backfill import backfill_job, job_lock
from app.domains.graph.mirror import (
    KNOWN_DEVICE_TYPES,
    _audio_device_changes,
    _publish_list,
    legacy_target,
)
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.lighting import schemas as lighting_schemas
from app.domains.lighting import service as lighting_service
from app.domains.lighting.models import DmxStep, DmxUniverse
from app.domains.video import service as video_service
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
    VideoPatchPoint,
)

router = APIRouter(
    prefix="/jobs/{job_id}/graph",
    tags=["graph:lists"],
    dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)],
)

MAX_BATCH = 200
NON_DEVICE_KINDS = (
    "channel",
    "output",
    "channel_list",
    "plot_element",
    "video_list",
    "video_input",
    "video_destination",
    "dmx_universe",
)


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
    if target is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node is not a device")
    if node.kind in NON_DEVICE_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node is not a device")
    changes = _audio_device_changes(
        {
            "name": node.name,
            "notes": node.notes,
            "position": node.position,
            "kind": node.kind if node.kind in KNOWN_DEVICE_TYPES else None,
            "attributes": node.attributes,
            "ports": node.ports,
            "stockwire_product_id": node.stockwire_product_id,
            "stockwire_product_name": node.stockwire_product_name,
        }
    )
    changes.setdefault("device_type", "other")
    device = await service.create_device(db, job_id, changes)
    node.legacy_ref = f"audio_devices:{device.id}"
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


@router.post(
    "/lists/{list_id}/outputs/batch",
    response_model=list[schemas.GraphDeviceRead],
    status_code=201,
)
async def create_outputs(
    job_id: UUID,
    list_id: UUID,
    payload: list[OutputCreate],
    db: AsyncSession = Depends(get_db),
) -> list[schemas.GraphDeviceRead]:
    """Add several outputs at once (the way ``/channels/batch`` adds inputs)."""
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} outputs")
    list_node = await _node(db, job_id, list_id, "channel_list")
    row = await _list_row(db, job_id, list_node)
    position = len(row.outputs)
    created = []
    for offset, item in enumerate(payload):
        created.append(
            await service.create_output(
                db, row.id, {**item.model_dump(exclude_unset=True), "position": position + offset}
            )
        )
    await _publish_list(db, job_id, row.id)
    await backfill_job(db, job_id)
    return [
        schemas.GraphDeviceRead.model_validate(
            await _by_ref(db, job_id, f"channel_list_outputs:{output.id}")
        )
        for output in created
    ]


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


class VideoListCreate(BaseModel):
    name: str = "Camera inputs"
    switcher_product_id: str | None = None
    switcher_product_name: str | None = None
    switcher_inputs: int | None = None
    switcher_outputs: int | None = None


class VideoInputCreate(BaseModel):
    input_number: int | None = Field(None, ge=1)
    source_label: str = ""
    source_type: str = "camera"
    connector: str = "sdi"
    notes: str = ""


class VideoOutputCreate(BaseModel):
    output_number: int | None = Field(None, ge=1)
    name: str = ""
    destination_label: str = ""
    connector: str = "sdi"
    notes: str = ""


class VideoStep(BaseModel):
    device_id: UUID
    connector: str = ""
    patch_label: str = ""
    notes: str = ""
    source_port: str = ""
    input_port: str = ""
    parent_index: int | None = None


class VideoChain(BaseModel):
    steps: list[VideoStep] = Field(default_factory=list, max_length=64)


async def _video_list(db: AsyncSession, job_id: UUID, node_id: UUID) -> VideoInputList:
    node = await _node(db, job_id, node_id, "video_list")
    row = await db.get(VideoInputList, _legacy_id(node, "video_input_lists"))
    if row is None or row.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video list not found")
    return row


@router.post("/video-lists", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_video_list(
    job_id: UUID, payload: VideoListCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    position = len(await video_service.list_input_lists(db, job_id))
    row = await video_service.save(
        db,
        VideoInputList(job_id=job_id, position=position, **payload.model_dump(exclude_unset=True)),
    )
    return await _read(db, job_id, f"video_input_lists:{row.id}")


async def _create_video_rows(
    db: AsyncSession, job_id: UUID, list_id: UUID, items: list, *, outputs: bool
) -> list[schemas.GraphDeviceRead]:
    lst = await _video_list(db, job_id, list_id)
    model, key, table = (
        (VideoOutput, "output_number", "video_outputs")
        if outputs
        else (VideoInput, "input_number", "video_inputs")
    )
    async with job_lock(job_id):
        number = await (
            video_service.next_output_number(db, lst.id)
            if outputs
            else video_service.next_input_number(db, lst.id)
        )
        rows = []
        for item in items:
            data = item.model_dump(exclude_unset=True)
            if data.get(key) is None:
                data[key] = number
            number = max(number, data[key]) + 1
            row = model(list_id=lst.id, **data)
            db.add(row)
            rows.append(row)
        await db.commit()
    db.expire_all()
    await backfill_job(db, job_id)
    return [
        schemas.GraphDeviceRead.model_validate(await _by_ref(db, job_id, f"{table}:{row.id}"))
        for row in rows
    ]


@router.post(
    "/video-lists/{list_id}/inputs", response_model=schemas.GraphDeviceRead, status_code=201
)
async def create_video_input(
    job_id: UUID, list_id: UUID, payload: VideoInputCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    return (await _create_video_rows(db, job_id, list_id, [payload], outputs=False))[0]


@router.post(
    "/video-lists/{list_id}/inputs/batch",
    response_model=list[schemas.GraphDeviceRead],
    status_code=201,
)
async def create_video_inputs(
    job_id: UUID,
    list_id: UUID,
    payload: list[VideoInputCreate],
    db: AsyncSession = Depends(get_db),
) -> list[schemas.GraphDeviceRead]:
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} inputs")
    return await _create_video_rows(db, job_id, list_id, payload, outputs=False)


@router.post(
    "/video-lists/{list_id}/outputs", response_model=schemas.GraphDeviceRead, status_code=201
)
async def create_video_output(
    job_id: UUID, list_id: UUID, payload: VideoOutputCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    return (await _create_video_rows(db, job_id, list_id, [payload], outputs=True))[0]


@router.post(
    "/video-lists/{list_id}/outputs/batch",
    response_model=list[schemas.GraphDeviceRead],
    status_code=201,
)
async def create_video_outputs(
    job_id: UUID,
    list_id: UUID,
    payload: list[VideoOutputCreate],
    db: AsyncSession = Depends(get_db),
) -> list[schemas.GraphDeviceRead]:
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} outputs")
    return await _create_video_rows(db, job_id, list_id, payload, outputs=True)


@router.post("/video-lists/{list_id}/fill-from-switcher")
async def fill_video_list_from_switcher(
    job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    lst = await _video_list(db, job_id, list_id)
    result = await video_service.fill_from_switcher(db, lst)
    db.expire_all()
    await backfill_job(db, job_id)
    return {k: (str(v) if k == "device_id" else v) for k, v in result.items()}


@router.put("/video-inputs/{input_id}/chain", response_model=ChainRead)
async def replace_video_input_chain(
    job_id: UUID, input_id: UUID, payload: VideoChain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, input_id, "video_input")
    row = await video_service.get_input(db, job_id, _legacy_id(node, "video_inputs"))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video input not found")
    for step in payload.steps:
        step_node = await db.get(GraphDevice, step.device_id)
        step_target = legacy_target(step_node) if step_node is not None else None
        step_device = (
            await service.get_device(db, step_target[1])
            if step_target is not None and step_target[0] == "audio_devices"
            else None
        )
        kind = step_device.device_type if step_device is not None else (step_node or node).kind
        if kind == "projector":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A projector takes its signal from a video output, not a video input",
            )
    twins = [await _device_twin(db, job_id, step.device_id) for step in payload.steps]
    for point in list(row.patch_points):
        await db.delete(point)
    await db.flush()
    for position, (step, twin) in enumerate(zip(payload.steps, twins, strict=True)):
        db.add(
            VideoPatchPoint(
                input_id=row.id,
                position=position,
                device_id=twin,
                connector=step.connector,
                patch_label=step.patch_label,
                notes=step.notes,
                source_port=step.source_port,
                input_port=step.input_port,
            )
        )
    await db.commit()
    db.expire_all()
    await backfill_job(db, job_id)
    return await _chain_edges(db, job_id, node)


@router.put("/video-outputs/{output_id}/chain", response_model=ChainRead)
async def replace_video_output_chain(
    job_id: UUID, output_id: UUID, payload: VideoChain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, output_id, "video_destination")
    row = await video_service.get_output(db, job_id, _legacy_id(node, "video_outputs"))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video output not found")
    for position, step in enumerate(payload.steps):
        if step.parent_index is not None and not 0 <= step.parent_index < position:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A step can only take its signal from an earlier step",
            )
    twins = [await _device_twin(db, job_id, step.device_id) for step in payload.steps]
    for point in list(row.patch_points):
        await db.delete(point)
    await db.flush()
    created: list[VideoOutputPatchPoint] = []
    for position, (step, twin) in enumerate(zip(payload.steps, twins, strict=True)):
        point = VideoOutputPatchPoint(
            output_id=row.id,
            position=position,
            device_id=twin,
            connector=step.connector,
            patch_label=step.patch_label,
            notes=step.notes,
            source_port=step.source_port,
            input_port=step.input_port,
            parent_id=created[step.parent_index].id if step.parent_index is not None else None,
        )
        db.add(point)
        await db.flush()
        created.append(point)
    await db.commit()
    db.expire_all()
    await backfill_job(db, job_id)
    return await _chain_edges(db, job_id, node)


EFFECTIVE_KEYS = {
    "patch_point_count",
    "input_default",
    "output_default",
    "input_count",
    "output_count",
    "input_source",
    "output_source",
    "stockwire_inputs",
    "stockwire_outputs",
    "stockwire_connectors",
    "weight_kg_effective",
    "weight_source",
    "power_watts_effective",
    "power_source",
}


@router.post("/audio-devices", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_audio_device(
    job_id: UUID, payload: audio_schemas.AudioDeviceCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Create a piece of gear (stagebox, mixer, camera, fixture, ...) with its ports and specs."""
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    device = await service.create_device(db, job_id, payload.model_dump(exclude_unset=True))
    return await _read(db, job_id, f"audio_devices:{device.id}")


@router.get("/effective")
async def effective_values(job_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, dict]:
    """Computed values per device node: I/O counts, weight and power and where they come from."""
    from app.domains.audio.router import _device_io_context, _to_device_read

    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await backfill_job(db, job_id)
    nodes = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == job_id, GraphDevice.legacy_ref.like("audio_devices:%")
            )
        )
    ).all()
    by_legacy = {legacy_target(n)[1]: n for n in nodes if legacy_target(n)}
    devices = [d for d in await service.list_devices(db, job_id) if d.id in by_legacy]
    context = await _device_io_context(db, job_id, devices)
    return {
        str(by_legacy[d.id].id): _to_device_read(d, context).model_dump(
            mode="json", include=EFFECTIVE_KEYS
        )
        for d in devices
    }


@router.post("/fixtures", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_fixture(
    job_id: UUID, payload: lighting_schemas.FixtureCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    """Create a fixture. Type-library rules and the first free DMX address apply as before.

    A fixture on a device lives on that device's node; otherwise it gets a node of its own.
    """
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    fixture = await lighting_service.create_fixture(
        db, job_id, payload.model_dump(exclude_unset=True)
    )
    ref = (
        f"audio_devices:{fixture.device_id}"
        if fixture.device_id
        else f"lighting_fixtures:{fixture.id}"
    )
    return await _read(db, job_id, ref)


class FixtureBulkItem(BaseModel):
    """One kind of fixture to add and how many of it."""

    fixture_type: str = ""
    channel_mode: str = ""
    device_name: str | None = None
    label: str = ""
    quantity: int = Field(1, ge=1, le=200)
    footprint: int | None = Field(None, ge=1, le=512)
    location: str = ""
    gel: str = ""
    notes: str = ""


class FixtureBulk(BaseModel):
    items: list[FixtureBulkItem] = Field(min_length=1, max_length=20)
    universe: int = Field(1, ge=1)
    start_address: int | None = Field(None, ge=1, le=512)
    spacing: int = Field(0, ge=0, le=512)


MAX_BULK_FIXTURES = 300


@router.post("/fixtures/bulk", response_model=list[schemas.GraphDeviceRead], status_code=201)
async def create_fixtures_bulk(
    job_id: UUID, payload: FixtureBulk, db: AsyncSession = Depends(get_db)
) -> list[schemas.GraphDeviceRead]:
    """Add several kinds of fixture at once, each a given number of times.

    Placement: with ``start_address`` the fixtures are laid out one after another from that
    address (footprint plus ``spacing`` apart), moving to the next universe when one does not fit
    before channel 512. Without it each one takes the first free address, starting in ``universe``.
    The footprint comes from the library type and mode (``apply_type``), so a mode chosen here
    sets it exactly as when adding a single fixture.
    """
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if sum(item.quantity for item in payload.items) > MAX_BULK_FIXTURES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BULK_FIXTURES} fixtures at once"
        )
    universe, cursor = payload.universe, payload.start_address
    refs: list[str] = []
    async with job_lock(job_id):
        for item in payload.items:
            base = item.model_dump(exclude={"quantity", "label"}, exclude_none=True)
            resolved = await lighting_service.apply_type(db, job_id, dict(base))
            footprint = resolved.get("footprint") or 1
            for number in range(1, item.quantity + 1):
                data = dict(base)
                label = item.label or item.fixture_type
                if label:
                    data["purpose"] = f"{label} {number}" if item.quantity > 1 else label
                data["universe"] = universe
                if cursor is not None:
                    if cursor + footprint - 1 > lighting_service.DMX_CHANNELS_PER_UNIVERSE:
                        universe, cursor = universe + 1, 1
                        data["universe"] = universe
                    data["dmx_address"] = cursor
                    cursor += footprint + payload.spacing
                else:
                    free = lighting_service.first_free_address(
                        await lighting_service.list_fixtures(db, job_id), universe, footprint
                    )
                    if free is None:
                        universe += 1
                        data["universe"] = universe
                fixture = await lighting_service.create_fixture(db, job_id, data)
                universe = fixture.universe or universe
                refs.append(
                    f"audio_devices:{fixture.device_id}"
                    if fixture.device_id
                    else f"lighting_fixtures:{fixture.id}"
                )
    db.expire_all()
    await backfill_job(db, job_id)
    out: list[schemas.GraphDeviceRead] = []
    for ref in dict.fromkeys(refs):
        out.append(schemas.GraphDeviceRead.model_validate(await _by_ref(db, job_id, ref)))
    return out


class UniverseCreate(BaseModel):
    number: int | None = Field(None, ge=1)
    name: str = ""
    source_device_id: UUID | None = None
    source_port: str = ""
    notes: str = ""


class UniverseSource(BaseModel):
    device_id: UUID | None = None
    port: str = ""


class DmxStepIn(BaseModel):
    device_id: UUID
    parent_index: int | None = None
    in_port: str = ""
    out_port: str = ""
    connector: str = ""
    notes: str = ""


class DmxChain(BaseModel):
    steps: list[DmxStepIn] = Field(default_factory=list, max_length=512)


@router.post("/universes", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_universe(
    job_id: UUID, payload: UniverseCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    source = (
        await _device_twin(db, job_id, payload.source_device_id)
        if payload.source_device_id
        else None
    )
    async with job_lock(job_id):
        existing = (await db.scalars(select(DmxUniverse).where(DmxUniverse.job_id == job_id))).all()
        number = payload.number or max((u.number for u in existing), default=0) + 1
        if any(u.number == number for u in existing):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Universe {number} already exists")
        universe = DmxUniverse(
            job_id=job_id,
            number=number,
            name=payload.name,
            notes=payload.notes,
            source_device_id=source,
            source_port=payload.source_port if source else "",
        )
        db.add(universe)
        await db.commit()
    return await _read(db, job_id, f"dmx_universes:{universe.id}")


@router.put("/universes/{universe_id}/source", response_model=schemas.GraphDeviceRead)
async def set_universe_source(
    job_id: UUID, universe_id: UUID, payload: UniverseSource, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    node = await _node(db, job_id, universe_id, "dmx_universe")
    universe = await db.get(DmxUniverse, _legacy_id(node, "dmx_universes"))
    if universe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Universe not found")
    universe.source_device_id = (
        await _device_twin(db, job_id, payload.device_id) if payload.device_id else None
    )
    universe.source_port = payload.port if payload.device_id else ""
    await db.commit()
    return await _read(db, job_id, node.legacy_ref)


async def _step_target(
    db: AsyncSession, job_id: UUID, node_id: UUID, fixtures_by_device: dict[UUID, UUID]
) -> dict:
    """A DMX step is either a fixture or a device; a device with a fixture steps as the fixture."""
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
    target = legacy_target(node)
    if target is not None and target[0] == "lighting_fixtures":
        return {"fixture_id": target[1]}
    device_id = await _device_twin(db, job_id, node_id)
    fixture_id = fixtures_by_device.get(device_id)
    return {"fixture_id": fixture_id} if fixture_id else {"device_id": device_id}


@router.put("/universes/{universe_id}/chain", response_model=ChainRead)
async def replace_universe_chain(
    job_id: UUID, universe_id: UUID, payload: DmxChain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, universe_id, "dmx_universe")
    legacy_id = _legacy_id(node, "dmx_universes")
    for position, step in enumerate(payload.steps):
        if step.parent_index is not None and not 0 <= step.parent_index < position:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A step can only take its signal from an earlier step",
            )
    fixtures_by_device: dict[UUID, UUID] = {}
    for fixture in await lighting_service.list_fixtures(db, job_id):
        if fixture.device_id:
            fixtures_by_device[fixture.device_id] = fixture.id  # the node shows the last one
    targets = [
        await _step_target(db, job_id, step.device_id, fixtures_by_device) for step in payload.steps
    ]
    await db.execute(delete(DmxStep).where(DmxStep.universe_id == legacy_id))
    created: list[DmxStep] = []
    for position, (step, target) in enumerate(zip(payload.steps, targets, strict=True)):
        row = DmxStep(
            universe_id=legacy_id,
            position=position,
            parent_id=created[step.parent_index].id if step.parent_index is not None else None,
            in_port=step.in_port,
            out_port=step.out_port,
            connector=step.connector,
            notes=step.notes,
            **target,
        )
        db.add(row)
        await db.flush()
        created.append(row)
    await db.commit()
    await backfill_job(db, job_id)
    return await _chain_edges(db, job_id, node)
