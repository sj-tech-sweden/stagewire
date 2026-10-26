from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import service as audio_service
from app.domains.auth.deps import get_current_user
from app.domains.video import schemas, service
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
    VideoPatchPoint,
)

router = APIRouter(tags=["video"], dependencies=[Depends(get_current_user)])


async def _job_or_404(db: AsyncSession, job_id: UUID) -> None:
    if await audio_service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")


async def _list_or_404(db: AsyncSession, job_id: UUID, list_id: UUID) -> VideoInputList:
    await _job_or_404(db, job_id)
    obj = await service.get_input_list(db, job_id, list_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Input list not found")
    return obj


async def _input_or_404(db: AsyncSession, job_id: UUID, input_id: UUID) -> VideoInput:
    await _job_or_404(db, job_id)
    obj = await service.get_input(db, job_id, input_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Input not found")
    return obj


async def _check_device(db: AsyncSession, job_id: UUID, device_id: UUID | None) -> None:
    if device_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A video patch point must be linked to a device"
        )
    if not await service.device_in_job(db, job_id, device_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device not found for this job")


@router.get("/jobs/{job_id}/video-lists", response_model=list[schemas.VideoInputListRead])
async def list_video_lists(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.VideoInputListRead]:
    await _job_or_404(db, job_id)
    lists = await service.list_input_lists(db, job_id)
    return [schemas.VideoInputListRead.model_validate(lst) for lst in lists]


@router.post(
    "/jobs/{job_id}/video-lists",
    response_model=schemas.VideoInputListRead,
    status_code=201,
)
async def create_video_list(
    job_id: UUID,
    payload: schemas.VideoInputListCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoInputListRead:
    await _job_or_404(db, job_id)
    existing = await service.list_input_lists(db, job_id)
    obj = VideoInputList(
        job_id=job_id, position=len(existing), **payload.model_dump(exclude_unset=True)
    )
    obj = await service.save(db, obj)
    return schemas.VideoInputListRead.model_validate(obj)


@router.patch(
    "/jobs/{job_id}/video-lists/{list_id}",
    response_model=schemas.VideoInputListRead,
)
async def update_video_list(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.VideoInputListUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoInputListRead:
    obj = await _list_or_404(db, job_id, list_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is None:
        data.pop("name", None)
    obj = await service.apply(db, obj, data)
    return schemas.VideoInputListRead.model_validate(obj)


@router.delete("/jobs/{job_id}/video-lists/{list_id}", status_code=204)
async def delete_video_list(
    job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    obj = await _list_or_404(db, job_id, list_id)
    await service.delete(db, obj)


@router.post(
    "/jobs/{job_id}/video-lists/{list_id}/inputs",
    response_model=schemas.VideoInputRead,
    status_code=201,
)
async def create_video_input(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.VideoInputCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoInputRead:
    lst = await _list_or_404(db, job_id, list_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("input_number") is None:
        data["input_number"] = await service.next_input_number(db, lst.id)
    obj = VideoInput(list_id=lst.id, **data)
    obj = await service.save(db, obj)
    return schemas.VideoInputRead.model_validate(obj)


@router.post(
    "/jobs/{job_id}/video-lists/{list_id}/inputs/bulk",
    response_model=list[schemas.VideoInputRead],
    status_code=201,
)
async def bulk_create_video_inputs(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.VideoBulkInputs,
    db: AsyncSession = Depends(get_db),
) -> list[schemas.VideoInputRead]:
    lst = await _list_or_404(db, job_id, list_id)
    if payload.device_id is not None:
        await _check_device(db, job_id, payload.device_id)
    created = await service.bulk_create_inputs(db, lst, payload)
    return [schemas.VideoInputRead.model_validate(i) for i in created]


@router.post(
    "/jobs/{job_id}/video-lists/{list_id}/outputs",
    response_model=schemas.VideoOutputRead,
    status_code=201,
)
async def create_video_output(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.VideoOutputCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoOutputRead:
    lst = await _list_or_404(db, job_id, list_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("output_number") is None:
        data["output_number"] = await service.next_output_number(db, lst.id)
    obj = VideoOutput(list_id=lst.id, **data)
    obj = await service.save(db, obj)
    return schemas.VideoOutputRead.model_validate(obj)


@router.post(
    "/jobs/{job_id}/video-lists/{list_id}/outputs/bulk",
    response_model=list[schemas.VideoOutputRead],
    status_code=201,
)
async def bulk_create_video_outputs(
    job_id: UUID,
    list_id: UUID,
    payload: schemas.VideoBulkOutputs,
    db: AsyncSession = Depends(get_db),
) -> list[schemas.VideoOutputRead]:
    lst = await _list_or_404(db, job_id, list_id)
    if payload.device_id is not None:
        await _check_device(db, job_id, payload.device_id)
    created = await service.bulk_create_outputs(db, lst, payload)
    return [schemas.VideoOutputRead.model_validate(o) for o in created]


async def _output_or_404(db: AsyncSession, job_id: UUID, output_id: UUID) -> VideoOutput:
    await _job_or_404(db, job_id)
    obj = await service.get_output(db, job_id, output_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Output not found")
    return obj


@router.patch(
    "/jobs/{job_id}/video-outputs/{output_id}",
    response_model=schemas.VideoOutputRead,
)
async def update_video_output(
    job_id: UUID,
    output_id: UUID,
    payload: schemas.VideoOutputUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoOutputRead:
    obj = await _output_or_404(db, job_id, output_id)
    data = payload.model_dump(exclude_unset=True)
    for key in ("name", "destination_label", "connector", "notes"):
        if key in data and data[key] is None:
            data[key] = ""
    obj = await service.apply(db, obj, data)
    return schemas.VideoOutputRead.model_validate(obj)


@router.delete("/jobs/{job_id}/video-outputs/{output_id}", status_code=204)
async def delete_video_output(
    job_id: UUID, output_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    obj = await _output_or_404(db, job_id, output_id)
    await service.delete(db, obj)


@router.post(
    "/jobs/{job_id}/video-outputs/{output_id}/patch-points",
    response_model=schemas.VideoOutputPatchPointRead,
    status_code=201,
)
async def create_video_output_point(
    job_id: UUID,
    output_id: UUID,
    payload: schemas.VideoOutputPatchPointCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoOutputPatchPointRead:
    out = await _output_or_404(db, job_id, output_id)
    await _check_device(db, job_id, payload.device_id)
    obj = VideoOutputPatchPoint(output_id=out.id, **payload.model_dump(exclude_unset=True))
    obj = await service.save(db, obj)
    return schemas.VideoOutputPatchPointRead.model_validate(obj)


@router.patch(
    "/jobs/{job_id}/video-outputs/{output_id}/patch-points/{point_id}",
    response_model=schemas.VideoOutputPatchPointRead,
)
async def update_video_output_point(
    job_id: UUID,
    output_id: UUID,
    point_id: UUID,
    payload: schemas.VideoOutputPatchPointUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoOutputPatchPointRead:
    await _output_or_404(db, job_id, output_id)
    obj = await service.get_output_point(db, job_id, point_id)
    if obj is None or obj.output_id != output_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch point not found")
    data = payload.model_dump(exclude_unset=True)
    if "device_id" in data:
        await _check_device(db, job_id, data["device_id"])
    obj = await service.apply(db, obj, data)
    return schemas.VideoOutputPatchPointRead.model_validate(obj)


@router.delete(
    "/jobs/{job_id}/video-outputs/{output_id}/patch-points/{point_id}",
    status_code=204,
)
async def delete_video_output_point(
    job_id: UUID, output_id: UUID, point_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await _output_or_404(db, job_id, output_id)
    obj = await service.get_output_point(db, job_id, point_id)
    if obj is None or obj.output_id != output_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch point not found")
    await service.delete(db, obj)


@router.patch(
    "/jobs/{job_id}/video-inputs/{input_id}",
    response_model=schemas.VideoInputRead,
)
async def update_video_input(
    job_id: UUID,
    input_id: UUID,
    payload: schemas.VideoInputUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoInputRead:
    obj = await _input_or_404(db, job_id, input_id)
    obj = await service.apply(db, obj, payload.model_dump(exclude_unset=True, exclude_none=True))
    return schemas.VideoInputRead.model_validate(obj)


@router.delete("/jobs/{job_id}/video-inputs/{input_id}", status_code=204)
async def delete_video_input(
    job_id: UUID, input_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    obj = await _input_or_404(db, job_id, input_id)
    await service.delete(db, obj)


@router.post(
    "/jobs/{job_id}/video-inputs/{input_id}/patch-points",
    response_model=schemas.VideoPatchPointRead,
    status_code=201,
)
async def create_video_patch_point(
    job_id: UUID,
    input_id: UUID,
    payload: schemas.VideoPatchPointCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoPatchPointRead:
    inp = await _input_or_404(db, job_id, input_id)
    await _check_device(db, job_id, payload.device_id)
    obj = VideoPatchPoint(input_id=inp.id, **payload.model_dump(exclude_unset=True))
    obj = await service.save(db, obj)
    return schemas.VideoPatchPointRead.model_validate(obj)


@router.patch(
    "/jobs/{job_id}/video-inputs/{input_id}/patch-points/{point_id}",
    response_model=schemas.VideoPatchPointRead,
)
async def update_video_patch_point(
    job_id: UUID,
    input_id: UUID,
    point_id: UUID,
    payload: schemas.VideoPatchPointUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.VideoPatchPointRead:
    await _input_or_404(db, job_id, input_id)
    obj = await service.get_point(db, job_id, point_id)
    if obj is None or obj.input_id != input_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch point not found")
    data = payload.model_dump(exclude_unset=True)
    if "device_id" in data:
        await _check_device(db, job_id, data["device_id"])
    obj = await service.apply(db, obj, data)
    return schemas.VideoPatchPointRead.model_validate(obj)


@router.delete(
    "/jobs/{job_id}/video-inputs/{input_id}/patch-points/{point_id}",
    status_code=204,
)
async def delete_video_patch_point(
    job_id: UUID, input_id: UUID, point_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await _input_or_404(db, job_id, input_id)
    obj = await service.get_point(db, job_id, point_id)
    if obj is None or obj.input_id != input_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patch point not found")
    await service.delete(db, obj)
