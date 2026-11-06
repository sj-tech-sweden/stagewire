"""Graph-native channel lists: lists, channels, outputs and patch chains.

The graph API is the way to author these. While the legacy tables still exist they are written
as a shadow (so unmoved readers keep working) and the graph is synced straight after.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import schemas as audio_schemas
from app.domains.audio import service
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import (
    audio_native,
    devices_native,
    dmx_native,
    fixtures_native,
    schemas,
    video_native,
)
from app.domains.graph.backfill import backfill_job, job_lock
from app.domains.graph.ids import power_id_of, public_id
from app.domains.graph.mirror import (
    KNOWN_DEVICE_TYPES,
    _publish_list,
    legacy_target,
)
from app.domains.graph.models import ConnectionEdge, GraphDevice, belongs_to, scope_filter
from app.domains.lighting import schemas as lighting_schemas
from app.domains.lighting import service as lighting_service

router = APIRouter(
    prefix="/jobs/{job_id}/graph",
    tags=["graph:lists"],
    dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)],
)

# A venue Standard Base Rig reuses the incremental graph edits but has no legacy rows and no
# per-job websocket, so its routes use `dependencies=[Depends(get_current_user)]` only (no
# refresh_power_connectors, no backfill, no publish_job_event). The job-only parts of list/channel
# editing are not reused for venues yet; only audio-device creation is mirrored here.
venue_router = APIRouter(
    prefix="/venues/{venue_id}/graph",
    tags=["graph:lists:venue"],
    dependencies=[Depends(get_current_user)],
)

MAX_BATCH = 200
NON_DEVICE_KINDS = (
    "rigging_point",
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
    wireless_frequency_mhz: float | None = None
    wireless_group: str | None = None
    wireless_channel: str | None = None
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


async def _by_ref(
    db: AsyncSession, job_id: UUID | None, ref: str, venue_id: UUID | None = None
) -> GraphDevice:
    node = (
        await db.scalars(
            select(GraphDevice).where(
                scope_filter(GraphDevice, job_id, venue_id), GraphDevice.legacy_ref == ref
            )
        )
    ).first()
    if node is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Graph sync did not create it")
    return node


async def _read(
    db: AsyncSession, job_id: UUID | None, ref: str, venue_id: UUID | None = None
) -> schemas.GraphDeviceRead:
    if job_id is not None:
        await backfill_job(db, job_id)
    return schemas.GraphDeviceRead.model_validate(await _by_ref(db, job_id, ref, venue_id))


async def _device_twin(
    db: AsyncSession, job_id: UUID | None, node_id: UUID, venue_id: UUID | None = None
) -> UUID:
    """The device id of a graph node; a catalog item is made a device on demand."""
    node = await db.get(GraphDevice, node_id)
    if node is None or not belongs_to(node, job_id, venue_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
    target = legacy_target(node)
    if target is not None and target[0] == "device":
        return target[1]
    if target is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node is not a device")
    if node.kind in NON_DEVICE_KINDS or (node.domain == "power" and power_id_of(node) is not None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That node is not a device")
    # a catalog item becomes a device in place: it takes its own id as the device id
    devices_native.promote(node, KNOWN_DEVICE_TYPES)
    await db.commit()
    return node.id


async def _publish_graph(db: AsyncSession, job_id: UUID, nodes: list[GraphDevice]) -> None:
    await audio_native.publish_nodes(db, job_id, [n.id for n in nodes])


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
    node = await audio_native.find_node(db, audio_native.LIST, row.id, job_id)
    await _publish_graph(db, job_id, [node])
    await _publish_list(db, job_id, row.id)
    return schemas.GraphDeviceRead.model_validate(node)


async def _list_members(db: AsyncSession, list_node: GraphDevice, kind: str) -> list[GraphDevice]:
    rows = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.job_id == list_node.job_id, GraphDevice.kind == kind
            )
        )
    ).all()
    return sorted(
        (r for r in rows if (r.attributes or {}).get("list_id") == str(list_node.id)),
        key=lambda r: (r.position, r.created_at),
    )


async def _create_channels(
    db: AsyncSession, job_id: UUID, list_node_id: UUID, items: list[ChannelCreate]
) -> list[schemas.GraphDeviceRead]:
    list_node = await _node(db, job_id, list_node_id, "channel_list")
    async with job_lock(job_id):
        existing = await _list_members(db, list_node, "channel")
        next_number = max((c.position for c in existing), default=0) + 1
        created = []
        for item in items:
            data = item.model_dump(exclude_unset=True)
            if data.get("channel_number") is None:
                data["channel_number"] = next_number
            next_number = max(next_number, data["channel_number"]) + 1
            node = audio_native.channel_node(job_id, list_node, data)
            db.add(node)
            created.append(node)
        await db.flush()
        for node in created:
            await audio_native.plot_native_performer(db, node)
        await db.commit()
    await _publish_graph(db, job_id, created)
    devices = {}
    for node in created:
        row = audio_native.channel_row(node, devices)
        await publish_job_event(
            job_id, "channel.upsert", audio_schemas.AudioChannelPatchRead.model_validate(row)
        )
    return [schemas.GraphDeviceRead.model_validate(node) for node in created]


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


async def _create_outputs(
    db: AsyncSession, job_id: UUID, list_node_id: UUID, items: list[OutputCreate]
) -> list[schemas.GraphDeviceRead]:
    list_node = await _node(db, job_id, list_node_id, "channel_list")
    async with job_lock(job_id):
        position = len(await _list_members(db, list_node, "output"))
        created = [
            audio_native.output_node(
                job_id, list_node, item.model_dump(exclude_unset=True), position + offset
            )
            for offset, item in enumerate(items)
        ]
        db.add_all(created)
        await db.commit()
    await _publish_graph(db, job_id, created)
    await _publish_list(db, job_id, public_id(list_node))
    return [schemas.GraphDeviceRead.model_validate(node) for node in created]


@router.post("/lists/{list_id}/outputs", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_output(
    job_id: UUID, list_id: UUID, payload: OutputCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    return (await _create_outputs(db, job_id, list_id, [payload]))[0]


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
    return await _create_outputs(db, job_id, list_id, payload)


async def _chain_edges(db: AsyncSession, job_id: UUID, node: GraphDevice) -> ChainRead:
    edges = (await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))).all()
    mine = [e for e in edges if (e.attributes or {}).get("chain") == str(node.id)]
    mine.sort(key=lambda e: (e.attributes or {}).get("position") or 0)
    return ChainRead(edges=[schemas.ConnectionEdgeRead.model_validate(e) for e in mine])


async def _chain_points(
    db: AsyncSession, job_id: UUID, steps: list[ChainStep], *, output: bool
) -> list[dict]:
    """The points a chain replace stores: each step's device is made a real device first."""
    points: list[dict] = []
    for position, step in enumerate(steps):
        twin = await _device_twin(db, job_id, step.device_id)
        device = await service.get_device(db, twin)
        parent = (
            points[step.parent_index]["point_id"]
            if output and step.parent_index is not None
            else None
        )
        points.append(
            audio_native.new_point(
                position,
                step.device_id,
                step.point_type or (device.device_type if device else "other"),
                step,
                parent,
                output=output,
            )
        )
    return points


@router.put("/channels/{channel_id}/chain", response_model=ChainRead)
async def replace_channel_chain(
    job_id: UUID, channel_id: UUID, payload: Chain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, channel_id, "channel")
    points = await _chain_points(db, job_id, payload.steps, output=False)
    await audio_native.replace_points(db, node, points)
    await db.commit()
    await backfill_job(db, job_id)
    channel = await service.get_channel(db, public_id(node), job_id)
    await _publish_graph(db, job_id, [node])
    await publish_job_event(
        job_id, "channel.upsert", audio_schemas.AudioChannelPatchRead.model_validate(channel)
    )
    return await _chain_edges(db, job_id, node)


@router.put("/outputs/{output_id}/chain", response_model=ChainRead)
async def replace_output_chain(
    job_id: UUID, output_id: UUID, payload: Chain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, output_id, "output")
    for position, step in enumerate(payload.steps):
        if step.parent_index is not None and not 0 <= step.parent_index < position:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A step can only take its signal from an earlier step",
            )
    points = await _chain_points(db, job_id, payload.steps, output=True)
    await audio_native.replace_points(db, node, points)
    await db.commit()
    await backfill_job(db, job_id)
    await _publish_graph(db, job_id, [node])
    await _publish_list(db, job_id, UUID(node.attributes["channel_list_id"]))
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
    stockwire_product_id: str | None = None
    stockwire_product_name: str | None = None


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


async def _video_list_node(db: AsyncSession, job_id: UUID, node_id: UUID) -> GraphDevice:
    return await _node(db, job_id, node_id, "video_list")


@router.post("/video-lists", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_video_list(
    job_id: UUID, payload: VideoListCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    data = payload.model_dump(exclude_unset=True)
    async with job_lock(job_id):
        position = len(
            (
                await db.scalars(
                    select(GraphDevice.id).where(
                        GraphDevice.job_id == job_id, GraphDevice.kind == "video_list"
                    )
                )
            ).all()
        )
        node = GraphDevice(
            id=uuid4(),
            job_id=job_id,
            domain="video",
            kind="video_list",
            name=data.get("name") or "Camera inputs",
            position=position,
            stockwire_product_id=data.get("switcher_product_id"),
            stockwire_product_name=data.get("switcher_product_name"),
            attributes={
                key: data.get(key)
                for key in (
                    "switcher_product_id",
                    "switcher_product_name",
                    "switcher_inputs",
                    "switcher_outputs",
                )
            },
        )
        db.add(node)
        await db.commit()
    await db.refresh(node)
    return schemas.GraphDeviceRead.model_validate(node)


async def _create_video_rows(
    db: AsyncSession, job_id: UUID, list_id: UUID, items: list, *, outputs: bool
) -> list[schemas.GraphDeviceRead]:
    list_node = await _video_list_node(db, job_id, list_id)
    kind, key = (
        ("video_destination", "output_number") if outputs else ("video_input", "input_number")
    )
    make = video_native.video_output_node if outputs else video_native.video_input_node
    async with job_lock(job_id):
        number = max([m.position for m in await _list_members(db, list_node, kind)] or [0]) + 1
        rows = []
        for item in items:
            data = item.model_dump(exclude_unset=True)
            if data.get(key) is None:
                data[key] = number
            number = max(number, data[key]) + 1
            row = make(job_id, list_node, data)
            db.add(row)
            rows.append(row)
        await db.commit()
    return [schemas.GraphDeviceRead.model_validate(row) for row in rows]


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
    """Make the list match its switcher, the way a sound list follows its mixer.

    The switcher is a gear device tagged with the list (a device's ``video_list_id`` = the
    list's public id), made on first use. Inputs and outputs with no connection get one to it, and
    missing ones are added up to the switcher's size.
    """
    list_node = await _video_list_node(db, job_id, list_id)
    ref = public_id(list_node)
    attrs = list_node.attributes or {}
    device = await devices_native.find_with(db, job_id, "video_list_id", ref)
    if device is None:
        product = attrs.get("switcher_product_name") or "Switcher"
        device = await service.create_device(
            db,
            job_id,
            {
                "name": f"{list_node.name} · {product}",
                "device_type": "switcher",
                "video_list_id": ref,
                "stockwire_product_id": attrs.get("switcher_product_id"),
                "stockwire_product_name": attrs.get("switcher_product_name"),
            },
        )
    # the sync takes the job lock itself, so it runs before this handler takes it for the rows
    await backfill_job(db, job_id)
    switcher = await _by_ref(db, job_id, f"device:{device.id}")
    counts = {"inputs_added": 0, "inputs_patched": 0, "outputs_added": 0, "outputs_patched": 0}
    async with job_lock(job_id):
        for kind, wanted_key, make, noun in (
            ("video_input", "switcher_inputs", video_native.video_input_node, "inputs"),
            ("video_destination", "switcher_outputs", video_native.video_output_node, "outputs"),
        ):
            members = await _list_members(db, list_node, kind)
            for member in members:
                if not (member.attributes or {}).get("points"):
                    await video_native.rebuild(db, member, [video_native.new_point(0, switcher.id)])
                    counts[f"{noun}_patched"] += 1
            number = max([m.position for m in members] or [0]) + 1
            key = "input_number" if kind == "video_input" else "output_number"
            for offset in range(max(0, int(attrs.get(wanted_key) or 0) - len(members))):
                row = make(job_id, list_node, {key: number + offset})
                db.add(row)
                await db.flush()
                await video_native.rebuild(db, row, [video_native.new_point(0, switcher.id)])
                counts[f"{noun}_added"] += 1
        await db.commit()
    return {"device_id": str(device.id), **counts}


@router.put("/video-inputs/{input_id}/chain", response_model=ChainRead)
async def replace_video_input_chain(
    job_id: UUID, input_id: UUID, payload: VideoChain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, input_id, "video_input")
    await video_native.require_step_devices(db, job_id, [s.device_id for s in payload.steps])
    for step in payload.steps:
        if (await db.get(GraphDevice, step.device_id)).kind == "projector":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A projector takes its signal from a video output, not a video input",
            )
    for step in payload.steps:
        await _device_twin(db, job_id, step.device_id)
    await video_native.rebuild(
        db,
        node,
        [
            video_native.new_point(position, step.device_id, step)
            for position, step in enumerate(payload.steps)
        ],
    )
    await db.commit()
    return await _chain_edges(db, job_id, node)


@router.put("/video-outputs/{output_id}/chain", response_model=ChainRead)
async def replace_video_output_chain(
    job_id: UUID, output_id: UUID, payload: VideoChain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, output_id, "video_destination")
    for position, step in enumerate(payload.steps):
        if step.parent_index is not None and not 0 <= step.parent_index < position:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A step can only take its signal from an earlier step",
            )
    await video_native.require_step_devices(db, job_id, [s.device_id for s in payload.steps])
    for step in payload.steps:
        await _device_twin(db, job_id, step.device_id)
    points: list[dict] = []
    for position, step in enumerate(payload.steps):
        parent = points[step.parent_index]["point_id"] if step.parent_index is not None else None
        points.append(video_native.new_point(position, step.device_id, step, parent))
    await video_native.rebuild(db, node, points)
    await db.commit()
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
@venue_router.post("/audio-devices", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_audio_device(
    job_id: UUID | None = None,
    venue_id: UUID | None = None,
    payload: audio_schemas.AudioDeviceCreate = None,
    db: AsyncSession = Depends(get_db),
) -> schemas.GraphDeviceRead:
    """Create a piece of gear (stagebox, mixer, camera, fixture, ...) with its ports and specs."""
    if job_id is not None:
        if await service.get_job(db, job_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        device = await service.create_device(db, job_id, payload.model_dump(exclude_unset=True))
        return await _read(db, job_id, f"device:{device.id}")
    if venue_id is not None:
        from app.domains.venues import service as venue_service

        if await venue_service.get_venue(db, venue_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
        device = await service.create_device(
            db, None, payload.model_dump(exclude_unset=True), venue_id=venue_id
        )
        return await _read(db, None, f"device:{device.id}", venue_id=venue_id)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "A job or a venue is required")


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
                GraphDevice.job_id == job_id, GraphDevice.legacy_ref.like("device:%")
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
    host = await fixtures_native.host_of(db, job_id, fixture.id)
    return schemas.GraphDeviceRead.model_validate(host)


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
    fixture_ids: list[UUID] = []
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
                fixture_ids.append(fixture.id)
    hosts = await fixtures_native.host_nodes(db, job_id)
    unique = {hosts[fid].id: hosts[fid] for fid in fixture_ids}
    return [schemas.GraphDeviceRead.model_validate(host) for host in unique.values()]


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


async def _universe_nodes(db: AsyncSession, job_id: UUID) -> list[GraphDevice]:
    return list(
        (
            await db.scalars(
                select(GraphDevice).where(
                    GraphDevice.job_id == job_id, GraphDevice.kind == "dmx_universe"
                )
            )
        ).all()
    )


async def _step_node(db: AsyncSession, job_id: UUID, node_id: UUID) -> GraphDevice:
    """A step's node: a fixture as it is, any other gear made into a real device first."""
    node = await db.get(GraphDevice, node_id)
    if node is None or node.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
    own_fixture = fixtures_native.fixture_id_of(node) is not None and not node.legacy_ref
    if not own_fixture:  # a fixture node of its own is a step as it is; any other gear is a device
        await _device_twin(db, job_id, node_id)
    return node


@router.post("/universes", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_universe(
    job_id: UUID, payload: UniverseCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if payload.source_device_id:
        await _step_node(db, job_id, payload.source_device_id)
    async with job_lock(job_id):
        existing = await _universe_nodes(db, job_id)
        number = payload.number or max((u.attributes["number"] for u in existing), default=0) + 1
        if any(u.attributes["number"] == number for u in existing):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Universe {number} already exists")
        source = (
            {"device_id": str(payload.source_device_id), "port": payload.source_port}
            if payload.source_device_id
            else None
        )
        node = dmx_native.universe_node(job_id, number, payload.name, payload.notes, source)
        db.add(node)
        await db.flush()
        await dmx_native.rebuild(db, node)
        await db.commit()
    await db.refresh(node)
    return schemas.GraphDeviceRead.model_validate(node)


@router.put("/universes/{universe_id}/source", response_model=schemas.GraphDeviceRead)
async def set_universe_source(
    job_id: UUID, universe_id: UUID, payload: UniverseSource, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    node = await _node(db, job_id, universe_id, "dmx_universe")
    if payload.device_id:
        await _step_node(db, job_id, payload.device_id)
    node.attributes = {
        **node.attributes,
        "source_device_id": str(payload.device_id) if payload.device_id else None,
        "source_port": payload.port if payload.device_id else "",
    }
    await dmx_native.rebuild(db, node)
    await db.commit()
    await db.refresh(node)
    return schemas.GraphDeviceRead.model_validate(node)


@router.put("/universes/{universe_id}/chain", response_model=ChainRead)
async def replace_universe_chain(
    job_id: UUID, universe_id: UUID, payload: DmxChain, db: AsyncSession = Depends(get_db)
) -> ChainRead:
    node = await _node(db, job_id, universe_id, "dmx_universe")
    for position, step in enumerate(payload.steps):
        if step.parent_index is not None and not 0 <= step.parent_index < position:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A step can only take its signal from an earlier step",
            )
    await dmx_native.require_step_nodes(db, job_id, [s.device_id for s in payload.steps])
    for step in payload.steps:
        await _step_node(db, job_id, step.device_id)
    steps: list[dict] = []
    for position, step in enumerate(payload.steps):
        parent = steps[step.parent_index]["step_id"] if step.parent_index is not None else None
        steps.append(dmx_native.new_step(position, step.device_id, step, parent))
    await dmx_native.rebuild(db, node, steps)
    await db.commit()
    return await _chain_edges(db, job_id, node)
