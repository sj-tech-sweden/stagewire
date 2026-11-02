from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import (
    AudioDevice,
    ProductionJob,
)
from app.domains.graph import audio_native, plot_native

_POINT_STRING_FIELDS = {"connector", "patch_label", "notes", "point_type"}


def _clean_point_data(data: dict) -> dict:
    return {k: ("" if (k in _POINT_STRING_FIELDS and v is None) else v) for k, v in data.items()}


async def create_job(db: AsyncSession, data: dict) -> ProductionJob:
    job = ProductionJob(**data)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def list_jobs(
    db: AsyncSession,
    *,
    search: str | None = None,
    newest_first: bool = False,
    skip: int = 0,
    limit: int | None = None,
) -> tuple[list[ProductionJob], int]:
    """Jobs, optionally filtered by a text in the title, venue or Stockwire id and paged.

    Returns the page and the total number of matches, so a list can say how many there are.
    """
    query = select(ProductionJob)
    if search and search.strip():
        like = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(ProductionJob.title).like(like),
                func.lower(ProductionJob.venue_name).like(like),
                func.lower(func.coalesce(ProductionJob.stockwire_job_id, "")).like(like),
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    order = ProductionJob.created_at.desc() if newest_first else ProductionJob.created_at
    query = query.order_by(order).offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return list((await db.execute(query)).scalars().all()), int(total or 0)


async def get_job(db: AsyncSession, job_id: UUID) -> ProductionJob | None:
    return await db.get(ProductionJob, job_id)


DEVICE_CLEARABLE_KEYS = {
    "weight_kg",
    "power_watts",
    "fixture_type",
    "channel_mode",
    "footprint_channels",
    "default_gel",
    "sensor_width_mm",
    "focal_min_mm",
    "focal_max_mm",
    "max_distance_m",
    "throw_ratio_min",
    "throw_ratio_max",
    "image_aspect_ratio",
    "sound_list_id",
    "video_list_id",
    "stockwire_product_id",
    "stockwire_product_name",
    "input_override",
    "output_override",
}

PLOT_CLEARABLE_KEYS = {
    "linked_lens_device_id",
    "focal_mm",
    "linked_channel_id",
    "linked_patch_point_id",
    "linked_device_id",
    "linked_output_point_id",
    "linked_video_input_id",
}

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


# Channel lists, channels, outputs and patch points are graph nodes (graph/audio_native.py). These
# keep the service API the routers and exporters have always used and return objects shaped like
# the old rows (``patch_points`` / ``points`` / ``channels`` / ``outputs`` nested).


async def create_channel(db: AsyncSession, channel_list_id: UUID, data: dict):
    channel = await audio_native.create_channel(db, channel_list_id, data)
    await db.commit()
    return channel


async def list_channels(db: AsyncSession, channel_list_id: UUID) -> list:
    return await audio_native.list_channels(db, channel_list_id)


async def get_channel(db: AsyncSession, channel_id: UUID, job_id: UUID | None = None):
    return await audio_native.get_channel(db, channel_id, job_id)


async def update_channel(db: AsyncSession, channel, data: dict):
    # the audio nodes know their job; a channel is looked up by its public id
    updated = await audio_native.update_channel(db, channel.id, data, channel.job_id)
    await db.commit()
    return updated


async def delete_channel(db: AsyncSession, channel):
    """The ids of the nodes and edges removed (for the caller to publish)."""
    removed = await audio_native.delete_channel(db, channel.id, channel.job_id)
    await db.commit()
    return removed


async def create_patch_point(db: AsyncSession, channel_id: UUID, data: dict):
    point = await audio_native.create_point(db, audio_native.CHANNEL, channel_id, data)
    await db.commit()
    return point


async def get_patch_point(db: AsyncSession, channel_id: UUID, point_id: UUID):
    return await audio_native.get_point(db, audio_native.CHANNEL, channel_id, point_id)


async def update_patch_point(db: AsyncSession, point, data: dict):
    updated = await audio_native.update_point(
        db, audio_native.CHANNEL, point.channel_id, point.id, data
    )
    await db.commit()
    return updated


async def delete_patch_point(db: AsyncSession, point) -> None:
    await audio_native.delete_point(db, audio_native.CHANNEL, point.channel_id, point.id)
    await db.commit()


async def create_output(db: AsyncSession, channel_list_id: UUID, data: dict):
    output = await audio_native.create_output(db, channel_list_id, data)
    await db.commit()
    return output


async def get_output(db: AsyncSession, output_id: UUID, job_id: UUID | None = None):
    return await audio_native.get_output(db, output_id, job_id)


async def update_output(db: AsyncSession, output, data: dict):
    updated = await audio_native.update_output(db, output.id, data, output.job_id)
    await db.commit()
    return updated


async def delete_output(db: AsyncSession, output):
    removed = await audio_native.delete_output(db, output.id, output.job_id)
    await db.commit()
    return removed


async def create_output_point(db: AsyncSession, output_id: UUID, data: dict):
    point = await audio_native.create_point(db, audio_native.OUTPUT, output_id, data)
    await db.commit()
    return point


async def get_output_point(db: AsyncSession, output_id: UUID, point_id: UUID):
    return await audio_native.get_point(db, audio_native.OUTPUT, output_id, point_id)


async def update_output_point(db: AsyncSession, point, data: dict):
    updated = await audio_native.update_point(
        db, audio_native.OUTPUT, point.output_id, point.id, data
    )
    await db.commit()
    return updated


async def delete_output_point(db: AsyncSession, point) -> None:
    await audio_native.delete_point(db, audio_native.OUTPUT, point.output_id, point.id)
    await db.commit()


async def list_job_channels_with_points(db: AsyncSession, job_id: UUID) -> list:
    return await audio_native.job_channels(db, job_id)


async def create_channel_list(db: AsyncSession, job_id: UUID, data: dict):
    channel_list = await audio_native.create_list(db, job_id, data)
    await db.commit()
    return channel_list


async def list_channel_lists(db: AsyncSession, job_id: UUID) -> list:
    return await audio_native.load_lists(db, job_id)


async def get_channel_list(db: AsyncSession, list_id: UUID, job_id: UUID | None = None):
    return await audio_native.get_list(db, list_id, job_id)


async def update_channel_list(db: AsyncSession, channel_list, data: dict):
    updated = await audio_native.update_list(db, channel_list.id, data, channel_list.job_id)
    await db.commit()
    return updated


async def delete_channel_list(db: AsyncSession, channel_list):
    removed = await audio_native.delete_list(db, channel_list.id, channel_list.job_id)
    await db.commit()
    return removed


async def create_plot_element(db: AsyncSession, job_id: UUID, data: dict):
    """Plot elements are graph nodes (``graph/plot_native.py``); these return the old row shape."""
    element = await plot_native.create_element(db, job_id, data)
    await db.commit()
    return element


async def list_plot_elements(db: AsyncSession, job_id: UUID) -> list:
    return await plot_native.load_elements(db, job_id)


async def update_plot_element(db: AsyncSession, job_id: UUID, element_id: UUID, data: dict):
    # a null clears only the link and focal fields; elsewhere it means "not sent" (as before)
    data = {k: v for k, v in data.items() if v is not None or k in PLOT_CLEARABLE_KEYS}
    element = await plot_native.update_element(db, job_id, element_id, data)
    await db.commit()
    return element


async def delete_plot_element(db: AsyncSession, job_id: UUID, element_id: UUID):
    """The deleted element's node id and edge ids, or None when there is no such element."""
    deleted = await plot_native.delete_element(db, job_id, element_id)
    await db.commit()
    return deleted


async def create_device(db: AsyncSession, job_id: UUID, data: dict) -> AudioDevice:
    device = AudioDevice(job_id=job_id, **data)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def list_devices(db: AsyncSession, job_id: UUID) -> list[AudioDevice]:
    result = await db.execute(
        select(AudioDevice).where(AudioDevice.job_id == job_id).order_by(AudioDevice.position)
    )
    return list(result.scalars().all())


async def get_device(db: AsyncSession, device_id: UUID) -> AudioDevice | None:
    result = await db.execute(select(AudioDevice).where(AudioDevice.id == device_id))
    return result.scalars().first()


async def update_device(db: AsyncSession, device: AudioDevice, data: dict) -> AudioDevice:
    for key, value in data.items():
        if value is not None or key in DEVICE_CLEARABLE_KEYS:
            setattr(device, key, value)
    await db.commit()
    await db.refresh(device)
    return device


async def job_io_totals(db: AsyncSession, job_id: UUID) -> tuple[int, int]:
    return await audio_native.totals(db, job_id)


async def list_io_totals(db: AsyncSession, list_id: UUID) -> tuple[int, int]:
    return await audio_native.list_totals(db, list_id)


async def delete_device(db: AsyncSession, device: AudioDevice) -> None:
    await db.delete(device)
    await db.commit()
