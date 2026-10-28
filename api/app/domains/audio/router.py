from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.domains.audio import schemas, service
from app.domains.audio.camera_specs import resolve_camera_specs
from app.domains.audio.coverage import coverage_grid, sector_for
from app.domains.audio.device_specs import (
    effective_value,
    resolve_device_io,
    resolve_device_physical,
)
from app.domains.audio.exports import get_exporter, list_exporters
from app.domains.audio.exports.base import ConsoleExporter
from app.domains.audio.models import (
    AudioChannelPatch,
    ChannelList,
    ChannelListOutput,
    ProductionJob,
    StockwireRequirementLink,
)
from app.domains.audio.speaker_specs import resolve_speaker_specs
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.stockwire.client import StockwireClient
from app.domains.stockwire.config import load_integration_config
from app.domains.video import service as video_service

router = APIRouter(prefix="/jobs", tags=["audio:jobs"], dependencies=[Depends(get_current_user)])

MAX_COVERAGE_CELLS_PER_AXIS = 500


@router.post("", response_model=schemas.ProductionJobRead, status_code=201)
async def create_job(
    payload: schemas.ProductionJobCreate, db: AsyncSession = Depends(get_db)
) -> schemas.ProductionJobRead:
    job = await service.create_job(db, payload.model_dump())
    return schemas.ProductionJobRead.model_validate(job)


@router.get("", response_model=list[schemas.ProductionJobRead])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[schemas.ProductionJobRead]:
    jobs = await service.list_jobs(db)
    return [schemas.ProductionJobRead.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=schemas.ProductionJobRead)
async def get_job(job_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.ProductionJobRead:
    job = await service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    return schemas.ProductionJobRead.model_validate(job)


@router.patch("/{job_id}", response_model=schemas.ProductionJobRead)
async def update_job(
    job_id: UUID,
    payload: schemas.ProductionJobUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ProductionJobRead:
    job = await service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    job = await service.update_job(db, job, payload.model_dump(exclude_unset=True))
    read = schemas.ProductionJobRead.model_validate(job)
    await publish_job_event(job_id, "job.update", read)
    return read


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    job = await service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    await service.delete_job(db, job)


@router.post(
    "/{job_id}/channel-lists",
    response_model=schemas.ChannelListRead,
    status_code=201,
)
async def create_channel_list(
    job_id: UUID,
    payload: schemas.ChannelListCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ChannelListRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.create_channel_list(
        db, job_id, payload.model_dump(exclude_unset=True)
    )
    result = await db.execute(
        select(ChannelList)
        .where(ChannelList.id == channel_list.id)
        .options(
            selectinload(ChannelList.channels).selectinload(AudioChannelPatch.patch_points),
            selectinload(ChannelList.outputs).selectinload(ChannelListOutput.points),
        )
    )
    channel_list = result.scalars().first()
    read = schemas.ChannelListRead.model_validate(channel_list)
    await publish_job_event(job_id, "list.upsert", read)
    return read


@router.get("/{job_id}/channel-lists", response_model=list[schemas.ChannelListRead])
async def list_channel_lists(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.ChannelListRead]:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    lists = await service.list_channel_lists(db, job_id)
    return [schemas.ChannelListRead.model_validate(lst) for lst in lists]


@router.patch(
    "/{job_id}/channel-lists/{list_id}",
    response_model=schemas.ChannelListRead,
)
async def update_channel_list(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.ChannelListUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ChannelListRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    channel_list = await service.update_channel_list(
        db, channel_list, payload.model_dump(exclude_unset=True)
    )
    read = schemas.ChannelListRead.model_validate(channel_list)
    await publish_job_event(job_id, "list.upsert", read)
    return read


@router.delete("/{job_id}/channel-lists/{list_id}", status_code=204)
async def delete_channel_list(
    job_id: UUID,
    list_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    await service.delete_channel_list(db, channel_list)
    await publish_job_event(job_id, "list.delete", {"id": str(list_id)})


@router.get(
    "/{job_id}/channel-lists/{list_id}/export-plugins",
    response_model=list[schemas.ExportPluginInfo],
)
async def list_export_plugins(
    job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.ExportPluginInfo]:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    return [
        schemas.ExportPluginInfo(
            key=e.key,
            label=e.label,
            description=e.description,
            media_type=e.media_type,
            file_extension=e.file_extension,
        )
        for e in list_exporters()
    ]


@router.get("/{job_id}/channel-lists/{list_id}/export")
async def export_channel_list(
    job_id: UUID,
    list_id: UUID,
    plugin: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    exporter: ConsoleExporter | None = get_exporter(plugin)
    if exporter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown export plugin")
    result = exporter.export(channel_list, channel_list.channels, channel_list.outputs)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post(
    "/{job_id}/channel-lists/{list_id}/channels",
    response_model=schemas.AudioChannelPatchRead,
    status_code=201,
)
async def create_channel(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.AudioChannelPatchCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.AudioChannelPatchRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    channel = await service.create_channel(db, list_id, payload.model_dump(exclude_unset=True))
    channel = await service.get_channel(db, channel.id)
    read = schemas.AudioChannelPatchRead.model_validate(channel)
    await publish_job_event(job_id, "channel.upsert", read)
    return read


@router.get(
    "/{job_id}/channel-lists/{list_id}/channels",
    response_model=list[schemas.AudioChannelPatchRead],
)
async def list_channels(
    job_id: UUID,
    list_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[schemas.AudioChannelPatchRead]:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    channels = await service.list_channels(db, list_id)
    return [schemas.AudioChannelPatchRead.model_validate(c) for c in channels]


@router.patch(
    "/{job_id}/channels/{channel_id}",
    response_model=schemas.AudioChannelPatchRead,
)
async def update_channel(
    job_id: UUID,
    channel_id: UUID,
    payload: schemas.AudioChannelPatchUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.AudioChannelPatchRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel = await service.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    channel = await service.update_channel(db, channel, payload.model_dump(exclude_unset=True))
    channel = await service.get_channel(db, channel.id)
    read = schemas.AudioChannelPatchRead.model_validate(channel)
    list_obj = await service.get_channel_list(db, channel.channel_list_id)
    await publish_job_event(list_obj.job_id, "channel.upsert", read)
    return read


@router.delete("/{job_id}/channels/{channel_id}", status_code=204)
async def delete_channel(
    job_id: UUID,
    channel_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    channel = await service.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    list_obj = await service.get_channel_list(db, channel.channel_list_id)
    await service.delete_channel(db, channel)
    await publish_job_event(list_obj.job_id, "channel.delete", {"id": str(channel_id)})


async def _publish_channel(db: AsyncSession, channel: AudioChannelPatch) -> None:
    channel_list = await service.get_channel_list(db, channel.channel_list_id)
    read = schemas.AudioChannelPatchRead.model_validate(channel)
    await publish_job_event(channel_list.job_id, "channel.upsert", read)


async def _linked_device_type(db: AsyncSession, job_id: UUID, device_id: UUID) -> str:
    device = await service.get_device(db, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")
    return device.device_type


@router.post(
    "/{job_id}/channels/{channel_id}/patch-points",
    response_model=schemas.ChannelPatchPointRead,
    status_code=201,
)
async def create_patch_point(
    job_id: UUID,
    channel_id: UUID,
    payload: schemas.ChannelPatchPointCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ChannelPatchPointRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel = await service.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    if payload.device_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A patch point must be linked to a device"
        )
    data = payload.model_dump(exclude_unset=True)
    data["point_type"] = await _linked_device_type(db, job_id, payload.device_id)
    point = await service.create_patch_point(db, channel_id, data)
    await _publish_channel(db, channel)
    return schemas.ChannelPatchPointRead.model_validate(point)


@router.patch(
    "/{job_id}/channels/{channel_id}/patch-points/{point_id}",
    response_model=schemas.ChannelPatchPointRead,
)
async def update_patch_point(
    job_id: UUID,
    channel_id: UUID,
    point_id: UUID,
    payload: schemas.ChannelPatchPointUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ChannelPatchPointRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    point = await service.get_patch_point(db, point_id)
    if point is None or point.channel_id != channel_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch point not found")
    data = payload.model_dump(exclude_unset=True)
    if "device_id" in data:
        if data["device_id"] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "A patch point must be linked to a device"
            )
        data["point_type"] = await _linked_device_type(db, job_id, data["device_id"])
    point = await service.update_patch_point(db, point, data)
    channel = await service.get_channel(db, channel_id)
    await _publish_channel(db, channel)
    return schemas.ChannelPatchPointRead.model_validate(point)


@router.delete("/{job_id}/channels/{channel_id}/patch-points/{point_id}", status_code=204)
async def delete_patch_point(
    job_id: UUID,
    channel_id: UUID,
    point_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    point = await service.get_patch_point(db, point_id)
    if point is None or point.channel_id != channel_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch point not found")
    channel = await service.get_channel(db, channel_id)
    await service.delete_patch_point(db, point)
    await _publish_channel(db, channel)


async def _publish_by_channel_id(db: AsyncSession, channel_id: UUID) -> None:
    channel = await service.get_channel(db, channel_id)
    if channel:
        await _publish_channel(db, channel)


async def _publish_list(db: AsyncSession, job_id: UUID, list_id: UUID) -> None:
    lst = await service.get_channel_list(db, list_id)
    if lst:
        read = schemas.ChannelListRead.model_validate(lst)
        await publish_job_event(job_id, "list.upsert", read)


@router.post(
    "/{job_id}/channel-lists/{list_id}/outputs",
    response_model=schemas.ChannelListOutputRead,
    status_code=201,
)
async def create_output(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.ChannelListOutputCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ChannelListOutputRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    channel_list = await service.get_channel_list(db, list_id)
    if channel_list is None or channel_list.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    output = await service.create_output(db, list_id, payload.model_dump(exclude_unset=True))
    await _publish_list(db, job_id, list_id)
    return schemas.ChannelListOutputRead.model_validate(output)


@router.patch(
    "/{job_id}/channel-lists/{list_id}/outputs/{output_id}",
    response_model=schemas.ChannelListOutputRead,
)
async def update_output(
    job_id: UUID,
    list_id: UUID,
    output_id: UUID,
    payload: schemas.ChannelListOutputUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.ChannelListOutputRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    output = await service.get_output(db, output_id)
    if output is None or output.channel_list_id != list_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    output = await service.update_output(db, output, payload.model_dump(exclude_unset=True))
    await _publish_list(db, job_id, list_id)
    return schemas.ChannelListOutputRead.model_validate(output)


@router.delete("/{job_id}/channel-lists/{list_id}/outputs/{output_id}", status_code=204)
async def delete_output(
    job_id: UUID,
    list_id: UUID,
    output_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    output = await service.get_output(db, output_id)
    if output is None or output.channel_list_id != list_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    await service.delete_output(db, output)
    await _publish_list(db, job_id, list_id)


@router.post(
    "/{job_id}/channel-lists/{list_id}/outputs/{output_id}/points",
    response_model=schemas.OutputPatchPointRead,
    status_code=201,
)
async def create_output_point(
    job_id: UUID,
    list_id: UUID,
    output_id: UUID,
    payload: schemas.OutputPatchPointCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.OutputPatchPointRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    output = await service.get_output(db, output_id)
    if output is None or output.channel_list_id != list_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    if payload.device_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Every output point must be linked to a device"
        )
    data = payload.model_dump(exclude_unset=True)
    data["point_type"] = await _linked_device_type(db, job_id, payload.device_id)
    point = await service.create_output_point(db, output_id, data)
    await _publish_list(db, job_id, list_id)
    return schemas.OutputPatchPointRead.model_validate(point)


@router.patch(
    "/{job_id}/channel-lists/{list_id}/outputs/{output_id}/points/{point_id}",
    response_model=schemas.OutputPatchPointRead,
)
async def update_output_point(
    job_id: UUID,
    list_id: UUID,
    output_id: UUID,
    point_id: UUID,
    payload: schemas.OutputPatchPointUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.OutputPatchPointRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    point = await service.get_output_point(db, point_id)
    if point is None or point.output_id != output_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output point not found")
    data = payload.model_dump(exclude_unset=True)
    if "device_id" in data:
        if data["device_id"] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Every output point must be linked to a device",
            )
        data["point_type"] = await _linked_device_type(db, job_id, data["device_id"])
    point = await service.update_output_point(db, point, data)
    await _publish_list(db, job_id, list_id)
    return schemas.OutputPatchPointRead.model_validate(point)


@router.delete(
    "/{job_id}/channel-lists/{list_id}/outputs/{output_id}/points/{point_id}",
    status_code=204,
)
async def delete_output_point(
    job_id: UUID,
    list_id: UUID,
    output_id: UUID,
    point_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    point = await service.get_output_point(db, point_id)
    if point is None or point.output_id != output_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output point not found")
    await service.delete_output_point(db, point)
    await _publish_list(db, job_id, list_id)


@router.get(
    "/{job_id}/patch-sheets",
    response_model=list[schemas.PatchSheetRead],
)
async def list_patch_sheets(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.PatchSheetRead]:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    lists = await service.list_channel_lists(db, job_id)
    devices = {d.id: d for d in await service.list_devices(db, job_id)}
    sheets: dict[UUID, dict] = {}

    def _add(device_id, point_type, kind, owner, p, direction):
        if not device_id:
            return
        device = devices.get(device_id)
        if device is None:
            return
        sheet = sheets.setdefault(
            device_id,
            {
                "name": device.name or str(device.id),
                "point_type": point_type or "mixer",
                "rows": [],
            },
        )
        sheet["rows"].append((kind, owner, p, direction, None))

    for lst in lists:
        for ch in lst.channels:
            for pt in ch.patch_points:
                _add(pt.device_id, pt.point_type, "channel", ch, pt, "in")
        for output in lst.outputs:
            for op in output.points:
                _add(op.device_id, op.point_type, "output", output, op, "out")
    out: list[schemas.PatchSheetRead] = []
    for _device_id, data in sheets.items():
        rows = []
        for kind, owner, p, direction, chain_label in data["rows"]:
            if kind == "channel":
                point = schemas.ChannelPatchPointRead.model_validate(p)
                rows.append(
                    schemas.PatchSheetChannel(
                        kind="channel",
                        channel_id=owner.id,
                        channel_number=owner.channel_number,
                        source_label=owner.source_label,
                        input_type=owner.input_type,
                        device=owner.device,
                        phantom_power=owner.phantom_power,
                        notes=owner.notes,
                        direction=direction,
                        chain_label=chain_label,
                        point=point,
                    )
                )
            else:
                rows.append(
                    schemas.PatchSheetChannel(
                        kind="output",
                        channel_id=owner.id,
                        channel_number=0,
                        source_label="",
                        output_name=owner.name,
                        direction=direction,
                        chain_label=chain_label,
                        point=schemas.ChannelPatchPointRead(
                            id=p.id,
                            channel_id=owner.id,
                            position=p.position,
                            point_type=p.point_type,
                            device_id=p.device_id,
                            connector=p.connector,
                            patch_label=p.patch_label,
                            notes=p.notes,
                        ),
                    )
                )
        rows.sort(key=lambda r: (r.direction != "in", r.channel_number))
        out.append(
            schemas.PatchSheetRead(
                name=data["name"],
                device_id=_device_id,
                point_type=data["point_type"],
                channels=rows,
            )
        )
    out.sort(key=lambda s: s.name)
    return out


@router.post(
    "/{job_id}/plot-elements",
    response_model=schemas.StagePlotElementRead,
    status_code=201,
)
async def create_plot_element(
    job_id: UUID,
    payload: schemas.StagePlotElementCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.StagePlotElementRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    element = await service.create_plot_element(db, job_id, payload.model_dump(exclude_unset=True))
    return schemas.StagePlotElementRead.model_validate(element)


@router.get(
    "/{job_id}/plot-elements",
    response_model=list[schemas.StagePlotElementRead],
)
async def list_plot_elements(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.StagePlotElementRead]:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    elements = await service.list_plot_elements(db, job_id)
    return [schemas.StagePlotElementRead.model_validate(e) for e in elements]


async def stockwire_product_fetcher(db: AsyncSession):
    """Return an async product lookup, or None when the Stockwire integration is off."""
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        return None
    sw = StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])

    async def fetch(product_id: str) -> dict | None:
        return await sw.get_product(product_id)

    return fetch


async def _speaker_spec_map(db: AsyncSession, job_id: UUID, elements) -> dict[str, dict]:
    lists = await service.list_channel_lists(db, job_id)
    point_device = {
        str(pt.id): str(pt.device_id)
        for lst in lists
        for out in lst.outputs
        for pt in out.points
        if pt.device_id
    }
    devices = await service.list_devices(db, job_id)
    device_product = {str(d.id): d.stockwire_product_id for d in devices if d.stockwire_product_id}
    rows = [
        {
            **schemas.StagePlotElementRead.model_validate(e).model_dump(mode="json"),
            "id": str(e.id),
        }
        for e in elements
    ]
    for row in rows:
        row["linked_output_point_id"] = (
            str(row["linked_output_point_id"]) if row.get("linked_output_point_id") else None
        )
    fetch = await stockwire_product_fetcher(db)
    return await resolve_speaker_specs(rows, point_device, device_product, fetch)


@router.get("/{job_id}/camera-specs")
async def get_camera_specs(job_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    elements = await service.list_plot_elements(db, job_id)
    devices = await service.list_devices(db, job_id)
    device_rows = {
        str(d.id): {
            "id": str(d.id),
            "device_type": d.device_type,
            "stockwire_product_id": d.stockwire_product_id,
            "sensor_width_mm": d.sensor_width_mm,
            "focal_min_mm": d.focal_min_mm,
            "focal_max_mm": d.focal_max_mm,
            "max_distance_m": d.max_distance_m,
        }
        for d in devices
    }
    rows = [
        {
            "id": str(e.id),
            "linked_device_id": str(e.linked_device_id) if e.linked_device_id else None,
            "linked_lens_device_id": str(e.linked_lens_device_id)
            if e.linked_lens_device_id
            else None,
            "focal_mm": e.focal_mm,
        }
        for e in elements
    ]
    fetch = await stockwire_product_fetcher(db)
    return await resolve_camera_specs(rows, device_rows, fetch)


@router.get("/{job_id}/speaker-specs")
async def get_speaker_specs(job_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    elements = await service.list_plot_elements(db, job_id)
    return await _speaker_spec_map(db, job_id, elements)


@router.get("/{job_id}/coverage")
async def get_coverage(
    job_id: UUID,
    cell_cm: float = Query(25, ge=5, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    elements = await service.list_plot_elements(db, job_id)
    specs = await _speaker_spec_map(db, job_id, elements)
    sectors = []
    for element in elements:
        data = schemas.StagePlotElementRead.model_validate(element).model_dump()
        if str(element.id) in specs:
            data.update(
                {k: specs[str(element.id)][k] for k in ("coverage_angle_h", "coverage_distance_m")}
            )
        sector = sector_for(data, job.stage_x_cm, job.stage_y_cm)
        if sector is not None:
            sectors.append(sector)
    longest = max(job.venue_width_cm, job.venue_height_cm)
    cell = max(cell_cm, longest / MAX_COVERAGE_CELLS_PER_AXIS)
    return coverage_grid(job.venue_width_cm, job.venue_height_cm, sectors, cell)


@router.patch(
    "/{job_id}/plot-elements/{element_id}",
    response_model=schemas.StagePlotElementRead,
)
async def update_plot_element(
    job_id: UUID,
    element_id: UUID,
    payload: schemas.StagePlotElementUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.StagePlotElementRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    element = await service.update_plot_element(
        db, job_id, element_id, payload.model_dump(exclude_unset=True)
    )
    if element is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plot element not found")
    return schemas.StagePlotElementRead.model_validate(element)


@router.delete(
    "/{job_id}/plot-elements/{element_id}",
    status_code=204,
)
async def delete_plot_element(
    job_id: UUID,
    element_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    deleted = await service.delete_plot_element(db, job_id, element_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plot element not found")


IO_DEVICE_TYPES = {"mixer", "switcher", "router", "multiviewer"}
VIDEO_DEVICE_TYPES = {"switcher", "router", "multiviewer"}


def _effective_count(override, stockwire, default) -> tuple[int | None, str | None]:
    if override is not None:
        return override, "override"
    if stockwire is not None:
        return stockwire, "stockwire"
    if default is not None:
        return default, "patch"
    return None, None


async def _device_io_context(db: AsyncSession, job_id: UUID, devices) -> dict:
    channels, outputs = await service.job_io_totals(db, job_id)
    lists = {}
    for device in devices:
        if device.sound_list_id is not None and str(device.sound_list_id) not in lists:
            lists[str(device.sound_list_id)] = await service.list_io_totals(
                db, device.sound_list_id
            )
    video_inputs = await video_service.video_inputs_per_device(db, job_id)
    device_product = {
        str(d.id): d.stockwire_product_id
        for d in devices
        if d.stockwire_product_id and d.device_type in IO_DEVICE_TYPES
    }
    physical_product = {
        str(d.id): d.stockwire_product_id for d in devices if d.stockwire_product_id
    }
    fetch = await stockwire_product_fetcher(db) if physical_product else None
    specs = await resolve_device_io(device_product, fetch)
    physical = await resolve_device_physical(physical_product, fetch)
    return {
        "physical": physical,
        "channels": channels,
        "outputs": outputs,
        "lists": lists,
        "video_inputs": video_inputs,
        "video_outputs": await video_service.video_outputs_per_device(db, job_id),
        "specs": specs,
    }


async def _check_device_lists(db: AsyncSession, job_id: UUID, data: dict) -> None:
    from app.domains.video.models import VideoInputList

    if data.get("sound_list_id") is not None:
        found = await service.get_channel_list(db, data["sound_list_id"])
        if found is None or found.job_id != job_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Channel list not found for this job"
            )
    if data.get("video_list_id") is not None:
        found = await db.get(VideoInputList, data["video_list_id"])
        if found is None or found.job_id != job_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Video list not found for this job"
            )


def _to_device_read(device, ctx: dict) -> schemas.AudioDeviceRead:
    read = schemas.AudioDeviceRead.model_validate(device)
    read.patch_point_count = len(device.patch_points)
    key = str(device.id)
    phys = ctx["physical"].get(key, {})
    read.weight_kg_effective, read.weight_source = effective_value(
        phys.get("weight_kg"), device.weight_kg
    )
    read.power_watts_effective, read.power_source = effective_value(
        phys.get("power_watts"), device.power_watts
    )
    if device.device_type not in IO_DEVICE_TYPES:
        return read
    sw = ctx["specs"].get(key, {})
    if device.device_type in VIDEO_DEVICE_TYPES:
        input_default = ctx["video_inputs"].get(key, 0)
        output_default = ctx["video_outputs"].get(key, 0)
    else:
        if device.sound_list_id is not None:
            input_default, output_default = ctx["lists"].get(
                str(device.sound_list_id), (ctx["channels"], ctx["outputs"])
            )
        else:
            input_default = ctx["channels"]
            output_default = ctx["outputs"]
    read.input_default = input_default
    read.output_default = output_default
    read.input_count, read.input_source = _effective_count(
        device.input_override, sw.get("inputs"), input_default
    )
    read.output_count, read.output_source = _effective_count(
        device.output_override, sw.get("outputs"), output_default
    )
    read.stockwire_inputs = sw.get("inputs")
    read.stockwire_outputs = sw.get("outputs")
    read.stockwire_connectors = sw.get("connectors", [])
    return read


async def _device_read(db: AsyncSession, device) -> schemas.AudioDeviceRead:
    ctx = await _device_io_context(db, device.job_id, [device])
    return _to_device_read(device, ctx)


@router.post(
    "/{job_id}/devices",
    response_model=schemas.AudioDeviceRead,
    status_code=201,
)
async def create_device(
    job_id: UUID,
    payload: schemas.AudioDeviceCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.AudioDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    data = payload.model_dump(exclude_unset=True)
    await _check_device_lists(db, job_id, data)
    device = await service.create_device(db, job_id, data)
    read = await _device_read(db, device)
    await publish_job_event(job_id, "device.upsert", read)
    return read


@router.get("/{job_id}/devices", response_model=list[schemas.AudioDeviceRead])
async def list_devices(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.AudioDeviceRead]:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    devices = await service.list_devices(db, job_id)
    ctx = await _device_io_context(db, job_id, devices)
    return [_to_device_read(d, ctx) for d in devices]


@router.patch("/{job_id}/devices/{device_id}", response_model=schemas.AudioDeviceRead)
async def update_device(
    job_id: UUID,
    device_id: UUID,
    payload: schemas.AudioDeviceUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.AudioDeviceRead:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    device = await service.get_device(db, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    data = payload.model_dump(exclude_unset=True)
    await _check_device_lists(db, job_id, data)
    device = await service.update_device(db, device, data)
    read = await _device_read(db, device)
    await publish_job_event(job_id, "device.upsert", read)
    return read


@router.delete("/{job_id}/devices/{device_id}", status_code=204)
async def delete_device(
    job_id: UUID,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    device = await service.get_device(db, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    if (
        device.patch_points
        or device.output_points
        or await video_service.device_has_patch_points(db, device_id)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Move or delete the patch points on this device before removing it",
        )
    await service.delete_device(db, device)
    await publish_job_event(job_id, "device.delete", {"id": str(device_id)})


class StockwireSyncResult(BaseModel):
    stockwire_job_id: str | None = None
    item_count: int = 0
    added: list[str] = []
    removed: list[str] = []
    updated: list[str] = []
    unchanged: int = 0
    freetext_skipped: list[str] = []
    errors: list[str] = []
    message: str = ""


def _desired_stockwire_items(job: ProductionJob) -> tuple[dict[int, dict], list[str]]:
    """Catalog products used in the job, one entry per product with its total quantity.

    Each device that holds a product adds one unit. Freetext entries (no catalog
    product) cannot be pushed and are returned separately.
    """
    desired: dict[int, dict] = {}
    freetext: list[str] = []

    def put(product_id, name: str | None, slot: str, freetext_name: str | None = None) -> None:
        if not product_id:
            if freetext_name:
                freetext.append(freetext_name)
            return
        pid = int(product_id)
        entry = desired.setdefault(pid, {"quantity": 0, "label": name or "", "slots": []})
        entry["quantity"] += 1
        if name and not entry["label"]:
            entry["label"] = name
        entry["slots"].append(slot)

    for clist in job.channel_lists:
        put(
            clist.mixer_product_id,
            clist.mixer_product_name,
            f"{clist.name} mixer",
            freetext_name=clist.mixer_product_name,
        )
        for ch in clist.channels:
            slot = f"Ch {ch.channel_number} {ch.source_label or ''}".strip()
            put(
                ch.stockwire_product_id,
                ch.stockwire_product_name or ch.source_label,
                slot,
                freetext_name=ch.stockwire_product_name,
            )
            put(
                ch.stand_product_id,
                ch.stand_product_name or "Microphone stand",
                f"{slot} stand",
                freetext_name=ch.stand_product_name,
            )
    for device in job.devices:
        put(
            device.stockwire_product_id,
            device.stockwire_product_name or device.name,
            device.name or "device",
            freetext_name=device.stockwire_product_name,
        )
    return desired, freetext


def _product_key(product_id: int) -> str:
    return f"product:{product_id}"


@router.post("/{job_id}/sync-stockwire", response_model=StockwireSyncResult)
async def sync_job_to_stockwire(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> StockwireSyncResult:
    """Make the linked stockwire-rental job match this job's catalog products.

    One requirement per product, with the total quantity across all slots. Adds new
    products, updates changed quantities, removes products no longer used. Only
    requirements this sync created are touched.
    """
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stockwire integration is not configured")
    result = await db.execute(
        select(ProductionJob)
        .options(
            selectinload(ProductionJob.devices),
            selectinload(ProductionJob.channel_lists)
            .selectinload(ChannelList.channels)
            .selectinload(AudioChannelPatch.patch_points),
            selectinload(ProductionJob.channel_lists)
            .selectinload(ChannelList.outputs)
            .selectinload(ChannelListOutput.points),
        )
        .where(ProductionJob.id == job_id)
    )
    job = result.scalars().first()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    if not job.stockwire_job_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Create or link a Stockwire job for this job before adding devices",
        )

    target = job.stockwire_job_id
    desired, freetext = _desired_stockwire_items(job)
    sw = StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])

    links = (
        (
            await db.execute(
                select(StockwireRequirementLink).where(StockwireRequirementLink.job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    links_by_key = {link.item_key: link for link in links}

    added: list[str] = []
    removed: list[str] = []
    updated: list[str] = []
    unchanged = 0
    errors: list[str] = []

    # Remove products that are gone (or whose link was made by an older per-slot sync).
    for key, link in list(links_by_key.items()):
        pid = int(link.product_id)
        if pid in desired and key == _product_key(pid):
            continue
        label = link.product_name or link.product_id
        try:
            await sw.delete_requirement(link.rental_requirement_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Could not remove {label}: {exc}")
            continue
        await db.delete(link)
        links_by_key.pop(key)
        removed.append(label)
    await db.commit()

    for pid, want in desired.items():
        key = _product_key(pid)
        label = want["label"] or str(pid)
        notes = ", ".join(want["slots"]) if want["slots"] else None
        link = links_by_key.get(key)
        if link is not None:
            if link.quantity == want["quantity"]:
                unchanged += 1
                continue
            try:
                await sw.update_requirement(
                    link.rental_requirement_id,
                    {"quantity_required": want["quantity"], "notes": notes, "label": label},
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Could not update {label}: {exc}")
                continue
            updated.append(f"{label} {link.quantity}→{want['quantity']}")
            link.quantity = want["quantity"]
            link.product_name = label
            continue
        try:
            created = await sw.add_requirement(
                target,
                {
                    "product_id": pid,
                    "quantity_required": want["quantity"],
                    "label": label,
                    "notes": notes,
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Could not add {label}: {exc}")
            continue
        db.add(
            StockwireRequirementLink(
                job_id=job.id,
                item_key=key,
                product_id=str(pid),
                product_name=label,
                rental_requirement_id=int(created["id"]),
                quantity=want["quantity"],
            )
        )
        added.append(f"{label} ×{want['quantity']}")
    await db.commit()

    parts: list[str] = []
    if added:
        parts.append(f"added {len(added)}")
    if updated:
        parts.append(f"updated {len(updated)}")
    if removed:
        parts.append(f"removed {len(removed)}")
    parts.append(f"unchanged {unchanged}")
    message = ", ".join(parts)
    if freetext:
        message += f"; {len(freetext)} freetext item(s) not sent (no catalog product)"

    return StockwireSyncResult(
        stockwire_job_id=target,
        item_count=len(desired),
        added=added,
        removed=removed,
        updated=updated,
        unchanged=unchanged,
        freetext_skipped=freetext,
        errors=errors,
        message=message,
    )
