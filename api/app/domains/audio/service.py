from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.audio.models import (
    AudioChannelPatch,
    ChannelList,
    ChannelListOutput,
    ChannelPatchPoint,
    OutputPatchPoint,
    ProductionJob,
    StagePlotElement,
)

_POINT_STRING_FIELDS = {"name", "connector", "patch_label", "notes", "point_type"}


def _clean_point_data(data: dict) -> dict:
    return {k: ("" if (k in _POINT_STRING_FIELDS and v is None) else v) for k, v in data.items()}


async def create_job(db: AsyncSession, data: dict) -> ProductionJob:
    job = ProductionJob(**data)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def list_jobs(db: AsyncSession) -> list[ProductionJob]:
    result = await db.execute(select(ProductionJob).order_by(ProductionJob.created_at))
    return list(result.scalars().all())


async def get_job(db: AsyncSession, job_id: UUID) -> ProductionJob | None:
    return await db.get(ProductionJob, job_id)


# Stockwire link fields may be explicitly cleared (set to null) by the client.
CLEARABLE_KEYS = {
    "stockwire_product_id",
    "stockwire_product_name",
    "stand_product_id",
    "stand_product_name",
    "mixer_product_id",
    "mixer_product_name",
    "mixer_inputs",
    "mixer_buses",
    "stockwire_job_id",
    "device",
    "connector",
}


async def update_job(db: AsyncSession, job: ProductionJob, data: dict) -> ProductionJob:
    for key, value in data.items():
        if value is not None or key in CLEARABLE_KEYS:
            setattr(job, key, value)
    await db.commit()
    await db.refresh(job)
    return job


async def delete_job(db: AsyncSession, job: ProductionJob) -> None:
    await db.delete(job)
    await db.commit()


async def create_channel(db: AsyncSession, channel_list_id: UUID, data: dict) -> AudioChannelPatch:
    channel = AudioChannelPatch(channel_list_id=channel_list_id, **data)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


async def list_channels(db: AsyncSession, channel_list_id: UUID) -> list[AudioChannelPatch]:
    result = await db.execute(
        select(AudioChannelPatch)
        .where(AudioChannelPatch.channel_list_id == channel_list_id)
        .options(selectinload(AudioChannelPatch.patch_points))
        .order_by(AudioChannelPatch.channel_number)
    )
    return list(result.scalars().all())


async def get_channel(db: AsyncSession, channel_id: UUID) -> AudioChannelPatch | None:
    result = await db.execute(
        select(AudioChannelPatch)
        .options(selectinload(AudioChannelPatch.patch_points))
        .where(AudioChannelPatch.id == channel_id)
    )
    return result.scalars().first()


async def update_channel(
    db: AsyncSession, channel: AudioChannelPatch, data: dict
) -> AudioChannelPatch:
    for key, value in data.items():
        if value is not None or key in CLEARABLE_KEYS:
            setattr(channel, key, value)
    await db.commit()
    await db.refresh(channel)
    return channel


async def delete_channel(db: AsyncSession, channel: AudioChannelPatch) -> None:
    await db.delete(channel)
    await db.commit()


async def create_patch_point(db: AsyncSession, channel_id: UUID, data: dict) -> ChannelPatchPoint:
    data = _clean_point_data(data)
    point = ChannelPatchPoint(channel_id=channel_id, **data)
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


async def get_patch_point(db: AsyncSession, point_id: UUID) -> ChannelPatchPoint | None:
    return await db.get(ChannelPatchPoint, point_id)


async def update_patch_point(
    db: AsyncSession, point: ChannelPatchPoint, data: dict
) -> ChannelPatchPoint:
    for key, value in data.items():
        if value is not None or key in CLEARABLE_KEYS:
            setattr(point, key, value)
    await db.commit()
    await db.refresh(point)
    return point


async def delete_patch_point(db: AsyncSession, point: ChannelPatchPoint) -> None:
    await db.delete(point)
    await db.commit()


async def create_output(db: AsyncSession, channel_list_id: UUID, data: dict) -> ChannelListOutput:
    output = ChannelListOutput(channel_list_id=channel_list_id, **data)
    db.add(output)
    await db.commit()
    await db.refresh(output, ["points"])
    return output


async def get_output(db: AsyncSession, output_id: UUID) -> ChannelListOutput | None:
    result = await db.execute(
        select(ChannelListOutput)
        .options(selectinload(ChannelListOutput.points))
        .where(ChannelListOutput.id == output_id)
    )
    return result.scalars().first()


async def update_output(
    db: AsyncSession, output: ChannelListOutput, data: dict
) -> ChannelListOutput:
    for key, value in data.items():
        if value is not None or key in CLEARABLE_KEYS:
            setattr(output, key, value)
    await db.commit()
    await db.refresh(output, ["points"])
    return output


async def delete_output(db: AsyncSession, output: ChannelListOutput) -> None:
    await db.delete(output)
    await db.commit()


async def create_output_point(db: AsyncSession, output_id: UUID, data: dict) -> OutputPatchPoint:
    data = _clean_point_data(data)
    point = OutputPatchPoint(output_id=output_id, **data)
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point


async def get_output_point(db: AsyncSession, point_id: UUID) -> OutputPatchPoint | None:
    return await db.get(OutputPatchPoint, point_id)


async def update_output_point(
    db: AsyncSession, point: OutputPatchPoint, data: dict
) -> OutputPatchPoint:
    for key, value in data.items():
        if value is not None or key in CLEARABLE_KEYS:
            setattr(point, key, value)
    await db.commit()
    await db.refresh(point)
    return point


async def delete_output_point(db: AsyncSession, point: OutputPatchPoint) -> None:
    await db.delete(point)
    await db.commit()


async def list_job_channels_with_points(db: AsyncSession, job_id: UUID) -> list[AudioChannelPatch]:
    result = await db.execute(
        select(AudioChannelPatch)
        .join(AudioChannelPatch.channel_list)
        .options(selectinload(AudioChannelPatch.patch_points))
        .where(ChannelList.job_id == job_id)
        .order_by(AudioChannelPatch.channel_number)
    )
    return list(result.scalars().all())


async def create_channel_list(db: AsyncSession, job_id: UUID, data: dict) -> ChannelList:
    channel_list = ChannelList(job_id=job_id, **data)
    db.add(channel_list)
    await db.commit()
    await db.refresh(channel_list, ["channels"])
    return channel_list


async def list_channel_lists(db: AsyncSession, job_id: UUID) -> list[ChannelList]:
    result = await db.execute(
        select(ChannelList)
        .options(
            selectinload(ChannelList.channels).selectinload(AudioChannelPatch.patch_points),
            selectinload(ChannelList.outputs).selectinload(ChannelListOutput.points),
        )
        .where(ChannelList.job_id == job_id)
        .order_by(ChannelList.position)
    )
    return list(result.scalars().all())


async def get_channel_list(db: AsyncSession, list_id: UUID) -> ChannelList | None:
    result = await db.execute(
        select(ChannelList)
        .options(
            selectinload(ChannelList.channels).selectinload(AudioChannelPatch.patch_points),
            selectinload(ChannelList.outputs).selectinload(ChannelListOutput.points),
        )
        .where(ChannelList.id == list_id)
    )
    return result.scalars().first()


async def update_channel_list(
    db: AsyncSession, channel_list: ChannelList, data: dict
) -> ChannelList:
    for key, value in data.items():
        if value is not None or key in CLEARABLE_KEYS:
            setattr(channel_list, key, value)
    await db.commit()
    await db.refresh(channel_list, ["channels"])
    return channel_list


async def delete_channel_list(db: AsyncSession, channel_list: ChannelList) -> None:
    await db.delete(channel_list)
    await db.commit()


async def create_plot_element(db: AsyncSession, job_id: UUID, data: dict) -> StagePlotElement:
    element = StagePlotElement(job_id=job_id, **data)
    db.add(element)
    await db.commit()
    await db.refresh(element)
    return element


async def list_plot_elements(db: AsyncSession, job_id: UUID) -> list[StagePlotElement]:
    result = await db.execute(select(StagePlotElement).where(StagePlotElement.job_id == job_id))
    return list(result.scalars().all())
