from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio import service as audio_service
from app.domains.audio.device_specs import effective_value, resolve_device_physical
from app.domains.audio.models import StagePlotElement
from app.domains.lighting import service as lighting_service
from app.domains.lighting.models import LightingFixture
from app.domains.rigging.calc import Load
from app.domains.rigging.models import PowerCircuit, PowerDistro, RiggingPoint


async def _fetcher(db: AsyncSession):
    from app.domains.audio.router import stockwire_product_fetcher

    return await stockwire_product_fetcher(db)


async def collect_loads(db: AsyncSession, job_id: UUID) -> list[Load]:
    devices = await audio_service.list_devices(db, job_id)
    by_id = {str(device.id): device for device in devices}
    device_product = {str(d.id): d.stockwire_product_id for d in devices if d.stockwire_product_id}
    fetch = await _fetcher(db) if device_product else None
    physical = await resolve_device_physical(device_product, fetch)

    def values(device_id) -> tuple[str, float | None, float | None]:
        device = by_id.get(str(device_id)) if device_id else None
        if device is None:
            return "", None, None
        phys = physical.get(str(device.id), {})
        weight = effective_value(phys.get("weight_kg"), device.weight_kg)[0]
        power = effective_value(phys.get("power_watts"), device.power_watts)[0]
        return device.name, weight, power

    loads: list[Load] = []
    for fixture in await lighting_service.list_fixtures(db, job_id):
        name, weight, power = values(fixture.device_id)
        loads.append(
            Load(
                id=str(fixture.id),
                kind="fixture",
                label=name or f"Fixture {fixture.dmx_address or ''}".strip(),
                weight_kg=weight,
                power_w=power,
                rigging_point_id=str(fixture.rigging_point_id)
                if fixture.rigging_point_id
                else None,
                power_circuit_id=str(fixture.power_circuit_id)
                if fixture.power_circuit_id
                else None,
            )
        )
    elements = await audio_service.list_plot_elements(db, job_id)
    for element in elements:
        if not element.linked_device_id:
            continue
        name, weight, power = values(element.linked_device_id)
        loads.append(
            Load(
                id=str(element.id),
                kind="element",
                label=element.label or name or element.element_type,
                weight_kg=weight,
                power_w=power,
                rigging_point_id=str(element.rigging_point_id)
                if element.rigging_point_id
                else None,
                power_circuit_id=str(element.power_circuit_id)
                if element.power_circuit_id
                else None,
            )
        )
    return loads


async def list_points(db: AsyncSession, job_id: UUID) -> list[RiggingPoint]:
    result = await db.execute(
        select(RiggingPoint).where(RiggingPoint.job_id == job_id).order_by(RiggingPoint.position)
    )
    return list(result.scalars().all())


async def list_distros(db: AsyncSession, job_id: UUID) -> list[PowerDistro]:
    result = await db.execute(
        select(PowerDistro).where(PowerDistro.job_id == job_id).order_by(PowerDistro.position)
    )
    return list(result.scalars().all())


async def list_circuits(db: AsyncSession, job_id: UUID) -> list[PowerCircuit]:
    result = await db.execute(
        select(PowerCircuit)
        .join(PowerDistro, PowerCircuit.distro_id == PowerDistro.id)
        .where(PowerDistro.job_id == job_id)
        .order_by(PowerCircuit.position)
    )
    return list(result.scalars().all())


async def get_point(db: AsyncSession, job_id: UUID, point_id: UUID) -> RiggingPoint | None:
    result = await db.execute(
        select(RiggingPoint).where(RiggingPoint.id == point_id, RiggingPoint.job_id == job_id)
    )
    return result.scalars().first()


async def get_distro(db: AsyncSession, job_id: UUID, distro_id: UUID) -> PowerDistro | None:
    result = await db.execute(
        select(PowerDistro).where(PowerDistro.id == distro_id, PowerDistro.job_id == job_id)
    )
    return result.scalars().first()


async def get_circuit(db: AsyncSession, job_id: UUID, circuit_id: UUID) -> PowerCircuit | None:
    result = await db.execute(
        select(PowerCircuit)
        .join(PowerDistro, PowerCircuit.distro_id == PowerDistro.id)
        .where(PowerCircuit.id == circuit_id, PowerDistro.job_id == job_id)
    )
    return result.scalars().first()


async def next_position(db: AsyncSession, model, job_id: UUID) -> int:
    if model is PowerCircuit:
        count = await db.scalar(
            select(func.count(PowerCircuit.id))
            .join(PowerDistro, PowerCircuit.distro_id == PowerDistro.id)
            .where(PowerDistro.job_id == job_id)
        )
    else:
        count = await db.scalar(select(func.count(model.id)).where(model.job_id == job_id))
    return count or 0


async def save(db: AsyncSession, obj):
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def assign(db: AsyncSession, job_id: UUID, kind: str, load_id: UUID, data: dict) -> None:
    if kind == "fixture":
        target = await db.get(LightingFixture, load_id)
        valid = target is not None and target.job_id == job_id
    else:
        target = await db.get(StagePlotElement, load_id)
        valid = target is not None and target.job_id == job_id
    if not valid:
        raise LookupError("Load not found")
    for key, value in data.items():
        setattr(target, key, value)
    await db.commit()
