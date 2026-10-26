from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.audio.models import AudioDevice
from app.domains.video.models import VideoInput, VideoInputList, VideoPatchPoint


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
