import uuid
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import AudioDevice
from app.domains.lighting.models import LightingFixture

FIXTURE_DEVICE_TYPE = "fixture"
DMX_CHANNELS_PER_UNIVERSE = 512
TEXT_KEYS = ("fixture_type", "channel_mode", "location", "gel", "purpose", "notes")
FIELD_KEYS = {
    "universe",
    "dmx_address",
    "footprint",
    "fixture_type",
    "channel_mode",
    "location",
    "gel",
    "purpose",
    "notes",
}
DEVICE_DEFAULT_KEYS = {
    "fixture_type": "fixture_type",
    "channel_mode": "channel_mode",
    "footprint": "footprint_channels",
    "gel": "default_gel",
}


async def list_fixtures(db: AsyncSession, job_id: UUID) -> list[LightingFixture]:
    result = await db.execute(
        select(LightingFixture)
        .where(LightingFixture.job_id == job_id)
        .order_by(LightingFixture.position, LightingFixture.created_at)
    )
    return list(result.scalars().all())


async def get_fixture(db: AsyncSession, job_id: UUID, fixture_id: UUID) -> LightingFixture | None:
    result = await db.execute(
        select(LightingFixture).where(
            LightingFixture.id == fixture_id, LightingFixture.job_id == job_id
        )
    )
    return result.scalars().first()


def dmx_flags(fixtures: list[LightingFixture]) -> dict[UUID, tuple[bool, bool]]:
    """Per fixture: (overlaps another fixture in its universe, runs past channel 512)."""
    flags: dict[UUID, list[bool]] = {f.id: [False, False] for f in fixtures}
    spans: dict[int, list[tuple[int, int, UUID]]] = {}
    for fixture in fixtures:
        if fixture.universe is None or fixture.dmx_address is None:
            continue
        end = fixture.dmx_address + (fixture.footprint or 1) - 1
        if end > DMX_CHANNELS_PER_UNIVERSE:
            flags[fixture.id][1] = True
        spans.setdefault(fixture.universe, []).append((fixture.dmx_address, end, fixture.id))
    for items in spans.values():
        for index, (start, end, first) in enumerate(items):
            for other_start, other_end, second in items[index + 1 :]:
                if start <= other_end and other_start <= end:
                    flags[first][0] = True
                    flags[second][0] = True
    return {key: (value[0], value[1]) for key, value in flags.items()}


async def find_or_create_device(
    db: AsyncSession, job_id: UUID, name: str, defaults: dict
) -> tuple[AudioDevice, bool]:
    result = await db.execute(
        select(AudioDevice).where(
            AudioDevice.job_id == job_id,
            AudioDevice.device_type == FIXTURE_DEVICE_TYPE,
            func.lower(AudioDevice.name) == name.lower(),
        )
    )
    device = result.scalars().first()
    if device is None:
        device = AudioDevice(
            job_id=job_id,
            name=name,
            device_type=FIXTURE_DEVICE_TYPE,
            fixture_type=defaults.get("fixture_type") or None,
            channel_mode=defaults.get("channel_mode") or None,
            footprint_channels=defaults.get("footprint"),
            default_gel=defaults.get("gel") or None,
        )
        db.add(device)
        await db.flush()
        return device, True
    return device, False


async def apply_device(db: AsyncSession, job_id: UUID, data: dict) -> tuple[dict, bool]:
    """Turn ``device_name`` into ``device_id``; empty profile fields come from the device.

    Returns the cleaned data and whether a new fixture device was created.
    """
    if "device_name" not in data:
        return data, False
    name = (data.pop("device_name") or "").strip()
    if not name:
        data["device_id"] = None
        return data, False
    device, created = await find_or_create_device(db, job_id, name, data)
    data["device_id"] = device.id
    for key, attr in DEVICE_DEFAULT_KEYS.items():
        if data.get(key) in (None, "") and getattr(device, attr) not in (None, ""):
            data[key] = getattr(device, attr)
    return data, created


def _clean(data: dict) -> dict:
    cleaned = {k: v for k, v in data.items() if k in FIELD_KEYS or k == "device_id"}
    for key in TEXT_KEYS:
        if key in cleaned and cleaned[key] is None:
            cleaned[key] = ""
    return cleaned


async def create_fixture(db: AsyncSession, job_id: UUID, data: dict) -> LightingFixture:
    data, _ = await apply_device(db, job_id, dict(data))
    position = await db.scalar(
        select(func.count(LightingFixture.id)).where(LightingFixture.job_id == job_id)
    )
    fixture = LightingFixture(job_id=job_id, position=position or 0, **_clean(data))
    db.add(fixture)
    await db.commit()
    await db.refresh(fixture)
    return fixture


async def update_fixture(
    db: AsyncSession, job_id: UUID, fixture: LightingFixture, data: dict
) -> LightingFixture:
    data, _ = await apply_device(db, job_id, dict(data))
    for key, value in _clean(data).items():
        setattr(fixture, key, value)
    await db.commit()
    await db.refresh(fixture)
    return fixture


async def delete_fixture(db: AsyncSession, fixture: LightingFixture) -> None:
    await db.delete(fixture)
    await db.commit()


async def import_rows(
    db: AsyncSession, job_id: UUID, rows: list[dict], clear_imported: bool
) -> tuple[int, int, int]:
    """Insert parsed rows as one import batch. Returns (created, devices created, cleared)."""
    cleared = 0
    if clear_imported:
        result = await db.execute(
            delete(LightingFixture).where(
                LightingFixture.job_id == job_id,
                LightingFixture.import_batch_id.is_not(None),
            )
        )
        cleared = result.rowcount or 0
    batch = uuid.uuid4()
    start = await db.scalar(
        select(func.count(LightingFixture.id)).where(LightingFixture.job_id == job_id)
    )
    devices_created = 0
    for index, row in enumerate(rows):
        data, created = await apply_device(db, job_id, dict(row))
        devices_created += int(created)
        db.add(
            LightingFixture(
                job_id=job_id,
                position=(start or 0) + index,
                import_batch_id=batch,
                **_clean(data),
            )
        )
    await db.commit()
    return len(rows), devices_created, cleared
