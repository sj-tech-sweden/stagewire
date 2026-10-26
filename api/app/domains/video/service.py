from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.audio.models import AudioDevice
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
    VideoPatchPoint,
)


async def list_input_lists(db: AsyncSession, job_id: UUID) -> list[VideoInputList]:
    result = await db.execute(
        select(VideoInputList)
        .where(VideoInputList.job_id == job_id)
        .order_by(VideoInputList.position)
        .options(selectinload(VideoInputList.inputs).selectinload(VideoInput.patch_points))
    )
    return list(result.scalars().all())


async def get_input_list(db: AsyncSession, job_id: UUID, list_id: UUID) -> VideoInputList | None:
    result = await db.execute(
        select(VideoInputList).where(VideoInputList.id == list_id, VideoInputList.job_id == job_id)
    )
    return result.scalars().first()


async def get_input(db: AsyncSession, job_id: UUID, input_id: UUID) -> VideoInput | None:
    result = await db.execute(
        select(VideoInput)
        .join(VideoInputList, VideoInput.list_id == VideoInputList.id)
        .where(VideoInput.id == input_id, VideoInputList.job_id == job_id)
    )
    return result.scalars().first()


async def get_point(db: AsyncSession, job_id: UUID, point_id: UUID) -> VideoPatchPoint | None:
    result = await db.execute(
        select(VideoPatchPoint)
        .join(VideoInput, VideoPatchPoint.input_id == VideoInput.id)
        .join(VideoInputList, VideoInput.list_id == VideoInputList.id)
        .where(VideoPatchPoint.id == point_id, VideoInputList.job_id == job_id)
    )
    return result.scalars().first()


async def device_in_job(db: AsyncSession, job_id: UUID, device_id: UUID) -> bool:
    device = await db.get(AudioDevice, device_id)
    return device is not None and device.job_id == job_id


async def video_inputs_per_device(db: AsyncSession, job_id: UUID) -> dict[str, int]:
    result = await db.execute(
        select(VideoPatchPoint.device_id, func.count(func.distinct(VideoPatchPoint.input_id)))
        .join(VideoInput, VideoPatchPoint.input_id == VideoInput.id)
        .join(VideoInputList, VideoInput.list_id == VideoInputList.id)
        .where(VideoInputList.job_id == job_id, VideoPatchPoint.device_id.is_not(None))
        .group_by(VideoPatchPoint.device_id)
    )
    return {str(device_id): int(count) for device_id, count in result.all()}


async def video_outputs_per_device(db: AsyncSession, job_id: UUID) -> dict[str, int]:
    result = await db.execute(
        select(
            VideoOutputPatchPoint.device_id,
            func.count(func.distinct(VideoOutputPatchPoint.output_id)),
        )
        .join(VideoOutput, VideoOutputPatchPoint.output_id == VideoOutput.id)
        .join(VideoInputList, VideoOutput.list_id == VideoInputList.id)
        .where(VideoInputList.job_id == job_id, VideoOutputPatchPoint.device_id.is_not(None))
        .group_by(VideoOutputPatchPoint.device_id)
    )
    return {str(device_id): int(count) for device_id, count in result.all()}


async def device_has_patch_points(db: AsyncSession, device_id: UUID) -> bool:
    count = await db.scalar(
        select(func.count(VideoPatchPoint.id)).where(VideoPatchPoint.device_id == device_id)
    )
    return bool(count)


async def next_input_number(db: AsyncSession, list_id: UUID) -> int:
    current = await db.scalar(
        select(func.max(VideoInput.input_number)).where(VideoInput.list_id == list_id)
    )
    return int(current or 0) + 1


async def save(db: AsyncSession, obj):
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def apply(db: AsyncSession, obj, data: dict):
    for key, value in data.items():
        setattr(obj, key, value)
    await db.commit()
    await db.refresh(obj)
    return obj


async def delete(db: AsyncSession, obj) -> None:
    await db.delete(obj)
    await db.commit()


async def get_output(db: AsyncSession, job_id: UUID, output_id: UUID) -> VideoOutput | None:
    result = await db.execute(
        select(VideoOutput)
        .join(VideoInputList, VideoOutput.list_id == VideoInputList.id)
        .where(VideoOutput.id == output_id, VideoInputList.job_id == job_id)
    )
    return result.scalars().first()


async def get_output_point(
    db: AsyncSession, job_id: UUID, point_id: UUID
) -> VideoOutputPatchPoint | None:
    result = await db.execute(
        select(VideoOutputPatchPoint)
        .join(VideoOutput, VideoOutputPatchPoint.output_id == VideoOutput.id)
        .join(VideoInputList, VideoOutput.list_id == VideoInputList.id)
        .where(VideoOutputPatchPoint.id == point_id, VideoInputList.job_id == job_id)
    )
    return result.scalars().first()


async def next_output_number(db: AsyncSession, list_id: UUID) -> int:
    current = await db.scalar(
        select(func.max(VideoOutput.output_number)).where(VideoOutput.list_id == list_id)
    )
    return int(current or 0) + 1


async def bulk_create_inputs(db: AsyncSession, lst: VideoInputList, payload) -> list[VideoInput]:
    created: list[VideoInput] = []
    for i in range(payload.quantity):
        number = payload.start_number + i
        label = f"{payload.prefix} {number}".strip()
        inp = VideoInput(
            list_id=lst.id,
            input_number=number,
            source_label=label,
            source_type=payload.source_type,
            connector=payload.connector,
            notes="",
        )
        db.add(inp)
        if payload.device_id is not None:
            inp.patch_points.append(
                VideoPatchPoint(
                    position=0, connector=payload.connector, device_id=payload.device_id
                )
            )
        created.append(inp)
    await db.commit()
    for inp in created:
        await db.refresh(inp)
    return created


async def bulk_create_outputs(db: AsyncSession, lst: VideoInputList, payload) -> list[VideoOutput]:
    created: list[VideoOutput] = []
    for i in range(payload.quantity):
        number = payload.start_number + i
        out = VideoOutput(
            list_id=lst.id,
            output_number=number,
            name=f"{payload.prefix} {number}".strip(),
            destination_label="",
            connector=payload.connector,
            notes="",
        )
        db.add(out)
        if payload.device_id is not None:
            out.patch_points.append(
                VideoOutputPatchPoint(
                    position=0, connector=payload.connector, device_id=payload.device_id
                )
            )
        created.append(out)
    await db.commit()
    for out in created:
        await db.refresh(out)
    return created


async def _switcher_device(db: AsyncSession, lst: VideoInputList) -> AudioDevice:
    devices = (
        (
            await db.execute(
                select(AudioDevice)
                .where(AudioDevice.job_id == lst.job_id)
                .order_by(AudioDevice.position)
            )
        )
        .scalars()
        .all()
    )
    if lst.switcher_product_id:
        for dev in devices:
            if dev.stockwire_product_id == lst.switcher_product_id:
                return dev
    for dev in devices:
        if dev.device_type == "switcher":
            return dev
    device = AudioDevice(
        job_id=lst.job_id,
        name=lst.switcher_product_name or "Switcher",
        device_type="switcher",
        stockwire_product_id=lst.switcher_product_id,
        stockwire_product_name=lst.switcher_product_name,
    )
    db.add(device)
    await db.flush()
    return device


async def fill_from_switcher(db: AsyncSession, lst: VideoInputList) -> dict:
    """Make the list match its switcher, the way a sound list follows its mixer."""
    device = await _switcher_device(db, lst)
    added_inputs = 0
    patched_inputs = 0
    wanted_inputs = int(lst.switcher_inputs or 0)
    for inp in list(lst.inputs):
        if not inp.patch_points:
            db.add(VideoPatchPoint(input_id=inp.id, position=0, device_id=device.id))
            patched_inputs += 1
    current = len(lst.inputs)
    next_number = max([i.input_number for i in lst.inputs] or [0]) + 1
    for n in range(max(0, wanted_inputs - current)):
        inp = VideoInput(list_id=lst.id, input_number=next_number + n, source_label="")
        inp.patch_points.append(VideoPatchPoint(position=0, device_id=device.id))
        db.add(inp)
        added_inputs += 1

    added_outputs = 0
    patched_outputs = 0
    wanted_outputs = int(lst.switcher_outputs or 0)
    for out in list(lst.outputs):
        if not out.patch_points:
            db.add(VideoOutputPatchPoint(output_id=out.id, position=0, device_id=device.id))
            patched_outputs += 1
    current_out = len(lst.outputs)
    next_out = max([o.output_number for o in lst.outputs] or [0]) + 1
    for n in range(max(0, wanted_outputs - current_out)):
        out = VideoOutput(list_id=lst.id, output_number=next_out + n, name="")
        out.patch_points.append(VideoOutputPatchPoint(position=0, device_id=device.id))
        db.add(out)
        added_outputs += 1

    await db.commit()
    return {
        "device_id": device.id,
        "inputs_added": added_inputs,
        "inputs_patched": patched_inputs,
        "outputs_added": added_outputs,
        "outputs_patched": patched_outputs,
    }
