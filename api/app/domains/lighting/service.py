import uuid
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph import devices_native, fixtures_native
from app.domains.lighting.models import FixtureMode, FixtureType

FIXTURE_DEVICE_TYPE = "fixture"
DMX_CHANNELS_PER_UNIVERSE = 512
TEXT_KEYS = (
    "fixture_type",
    "channel_mode",
    "location",
    "gel",
    "purpose",
    "notes",
    "power_connector",
)
FIELD_KEYS = {
    "fixture_type_id",
    "fixture_mode_id",
    "rigging_point_id",
    "power_node_id",
    "power_connector",
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


async def list_fixtures(db: AsyncSession, job_id: UUID):
    """The job's fixtures (graph-backed objects shaped like the old rows)."""
    return await fixtures_native.load_fixtures(db, job_id)


async def list_types(db: AsyncSession, job_id: UUID) -> list[FixtureType]:
    result = await db.execute(
        select(FixtureType).where(FixtureType.job_id == job_id).order_by(FixtureType.name)
    )
    return list(result.scalars().all())


async def get_type(db: AsyncSession, job_id: UUID, type_id: UUID) -> FixtureType | None:
    result = await db.execute(
        select(FixtureType).where(FixtureType.id == type_id, FixtureType.job_id == job_id)
    )
    return result.scalars().first()


async def get_mode(db: AsyncSession, job_id: UUID, mode_id: UUID) -> FixtureMode | None:
    result = await db.execute(
        select(FixtureMode)
        .join(FixtureType, FixtureMode.fixture_type_id == FixtureType.id)
        .where(FixtureMode.id == mode_id, FixtureType.job_id == job_id)
    )
    return result.scalars().first()


async def find_type(db: AsyncSession, job_id: UUID, name: str) -> FixtureType | None:
    result = await db.execute(
        select(FixtureType).where(
            FixtureType.job_id == job_id, func.lower(FixtureType.name) == name.lower()
        )
    )
    return result.scalars().first()


async def find_or_create_type(
    db: AsyncSession, job_id: UUID, name: str, source: str
) -> FixtureType:
    found = await find_type(db, job_id, name)
    if found is not None:
        return found
    fixture_type = FixtureType(job_id=job_id, name=name, source=source, modes=[])
    db.add(fixture_type)
    await db.flush()
    return fixture_type


async def ensure_mode(
    db: AsyncSession, fixture_type: FixtureType, name: str, footprint: int | None
) -> FixtureMode | None:
    """The named mode of a type, created with its footprint when it does not exist yet."""
    for mode in fixture_type.modes:
        if mode.name.lower() == name.lower():
            return mode
    if footprint is None:
        return None
    mode = FixtureMode(
        fixture_type_id=fixture_type.id,
        name=name,
        footprint=footprint,
        position=len(fixture_type.modes),
    )
    db.add(mode)
    await db.flush()
    fixture_type.modes.append(mode)
    return mode


async def apply_type(db: AsyncSession, job_id: UUID, data: dict) -> dict:
    """Resolve the fixture type and mode. A chosen type/mode sets the text and footprint; text
    from a CSV or MVR row creates the type and mode when they are missing.
    """
    type_modes = data.pop("type_modes", None) or {}
    fixture_type = None
    if data.get("fixture_type_id"):
        fixture_type = await get_type(db, job_id, data["fixture_type_id"])
    elif data.get("fixture_mode_id"):
        mode = await get_mode(db, job_id, data["fixture_mode_id"])
        if mode is not None:
            fixture_type = await get_type(db, job_id, mode.fixture_type_id)
            data["fixture_type_id"] = fixture_type.id
    elif (data.get("fixture_type") or "").strip():
        fixture_type = await find_or_create_type(
            db, job_id, data["fixture_type"].strip(), "mvr" if type_modes else "manual"
        )
        data["fixture_type_id"] = fixture_type.id
    if fixture_type is None:
        return data
    data["fixture_type"] = fixture_type.name
    for name, footprint in type_modes.items():
        await ensure_mode(db, fixture_type, name, footprint)

    mode = None
    if data.get("fixture_mode_id"):
        mode = await get_mode(db, job_id, data["fixture_mode_id"])
    elif (data.get("channel_mode") or "").strip():
        mode = await ensure_mode(
            db, fixture_type, data["channel_mode"].strip(), data.get("footprint")
        )
    if mode is not None:
        data["fixture_mode_id"] = mode.id
        data["channel_mode"] = mode.name
        data["footprint"] = mode.footprint
    elif "fixture_type_id" in data and "fixture_mode_id" not in data:
        data["fixture_mode_id"] = None
    return data


async def get_fixture(db: AsyncSession, job_id: UUID, fixture_id: UUID):
    return await fixtures_native.get_fixture(db, job_id, fixture_id)


def dmx_flags(fixtures: list) -> dict[UUID, tuple[bool, bool]]:
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
) -> tuple[SimpleNamespace, bool]:
    for device in await devices_native.load_devices(db, job_id):
        if (
            device.device_type == FIXTURE_DEVICE_TYPE
            and (device.name or "").lower() == name.lower()
        ):
            return device, False
    device = await devices_native.create_device(
        db,
        job_id,
        {
            "name": name,
            "device_type": FIXTURE_DEVICE_TYPE,
            "fixture_type": defaults.get("fixture_type") or None,
            "channel_mode": defaults.get("channel_mode") or None,
            "footprint_channels": defaults.get("footprint"),
            "default_gel": defaults.get("gel") or None,
        },
    )
    return device, True


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


def first_free_address(
    fixtures: list, universe: int, footprint: int, exclude_id: UUID | None = None
) -> int | None:
    """The lowest DMX address where a fixture of this footprint fits in the universe."""
    taken = [False] * (DMX_CHANNELS_PER_UNIVERSE + 1)
    for fixture in fixtures:
        if fixture.id == exclude_id or fixture.universe != universe or fixture.dmx_address is None:
            continue
        last = min(DMX_CHANNELS_PER_UNIVERSE, fixture.dmx_address + (fixture.footprint or 1) - 1)
        for channel in range(fixture.dmx_address, last + 1):
            taken[channel] = True
    width = min(max(footprint, 1), DMX_CHANNELS_PER_UNIVERSE)
    for start in range(1, DMX_CHANNELS_PER_UNIVERSE - width + 2):
        if not any(taken[start : start + width]):
            return start
    return None


async def _device_node_ready(db: AsyncSession, job_id: UUID, data: dict) -> None:
    """A fixture on a device lives on the device's graph node, which the sync makes: sync first
    when the device is new (the sync runs inside the job lock when the caller already holds it)."""
    if data.get("device_id"):
        from app.domains.graph.backfill import backfill_job

        await db.flush()
        await backfill_job(db, job_id)


async def create_fixture(db: AsyncSession, job_id: UUID, data: dict):
    data = await apply_type(db, job_id, dict(data))
    data, _ = await apply_device(db, job_id, data)
    if data.get("dmx_address") is None:
        universe = data.get("universe") or 1
        data["universe"] = universe
        data["dmx_address"] = first_free_address(
            await list_fixtures(db, job_id), universe, data.get("footprint") or 1
        )
    await _device_node_ready(db, job_id, data)
    fixture = await fixtures_native.create_fixture(db, job_id, _clean(data))
    await db.commit()
    return fixture


async def update_fixture(db: AsyncSession, job_id: UUID, fixture, data: dict):
    data = await apply_type(db, job_id, dict(data))
    data, _ = await apply_device(db, job_id, data)
    cleaned = _clean(data)
    if "device_id" in cleaned and cleaned["device_id"] != fixture.device_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A fixture's device cannot be changed; make a new fixture",
        )
    cleaned.pop("device_id", None)
    updated = await fixtures_native.update_fixture(db, job_id, fixture.id, cleaned)
    await db.commit()
    return updated


async def delete_fixture(db: AsyncSession, fixture) -> None:
    await fixtures_native.delete_fixture(db, fixture.job_id, fixture.id)
    await db.commit()


async def import_rows(
    db: AsyncSession, job_id: UUID, rows: list[dict], clear_imported: bool
) -> tuple[int, int, int]:
    """Insert parsed rows as one import batch. Returns (created, devices created, cleared)."""
    cleared = 0
    if clear_imported:
        for fixture in await list_fixtures(db, job_id):
            if fixture.import_batch_id is not None:
                await fixtures_native.delete_fixture(db, job_id, fixture.id)
                cleared += 1
    batch = uuid.uuid4()
    devices_created = 0
    for row in rows:
        data = await apply_type(db, job_id, dict(row))
        data, created = await apply_device(db, job_id, data)
        devices_created += int(created)
        await _device_node_ready(db, job_id, data)
        await fixtures_native.create_fixture(db, job_id, {**_clean(data), "import_batch_id": batch})
    await db.commit()
    return len(rows), devices_created, cleared


async def create_type(db: AsyncSession, job_id: UUID, data: dict) -> FixtureType:
    fixture_type = FixtureType(job_id=job_id, source="manual", modes=[], **data)
    db.add(fixture_type)
    await db.commit()
    await db.refresh(fixture_type)
    return fixture_type


async def update_type(db: AsyncSession, fixture_type: FixtureType, data: dict) -> FixtureType:
    for key, value in data.items():
        setattr(fixture_type, key, value)
    await db.commit()
    await db.refresh(fixture_type)
    return fixture_type


async def delete_type(db: AsyncSession, fixture_type: FixtureType) -> None:
    await db.delete(fixture_type)
    await db.commit()


async def create_mode(db: AsyncSession, fixture_type: FixtureType, data: dict) -> FixtureMode:
    mode = FixtureMode(fixture_type_id=fixture_type.id, position=len(fixture_type.modes), **data)
    db.add(mode)
    await db.commit()
    await db.refresh(mode)
    return mode


async def update_mode(db: AsyncSession, mode: FixtureMode, data: dict) -> FixtureMode:
    for key, value in data.items():
        setattr(mode, key, value)
    await db.commit()
    await db.refresh(mode)
    return mode


async def delete_mode(db: AsyncSession, mode: FixtureMode) -> None:
    await db.delete(mode)
    await db.commit()


async def import_stockwire_type(
    db: AsyncSession, job_id: UUID, product_id: str, values: dict
) -> FixtureType:
    """Create or refresh the type for a Stockwire product, with the product's modes."""
    result = await db.execute(
        select(FixtureType).where(
            FixtureType.job_id == job_id, FixtureType.stockwire_product_id == product_id
        )
    )
    fixture_type = result.scalars().first()
    if fixture_type is None:
        fixture_type = FixtureType(
            job_id=job_id, source="stockwire", stockwire_product_id=product_id, modes=[]
        )
        db.add(fixture_type)
        await db.flush()
    fixture_type.name = values["name"]
    fixture_type.manufacturer = values["manufacturer"]
    fixture_type.category = values["category"]
    fixture_type.weight_kg = values["weight_kg"]
    fixture_type.power_watts = values["power_watts"]
    for item in values["modes"]:
        mode = next((m for m in fixture_type.modes if m.name == item["name"]), None)
        if mode is None:
            mode = FixtureMode(
                fixture_type_id=fixture_type.id,
                name=item["name"],
                footprint=item["footprint"],
                position=len(fixture_type.modes),
            )
            db.add(mode)
            fixture_type.modes.append(mode)
        else:
            mode.footprint = item["footprint"]
    await db.commit()
    await db.refresh(fixture_type)
    return fixture_type
