from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio import service as audio_service
from app.domains.audio.device_specs import effective_value, resolve_device_physical
from app.domains.graph import power_native, rigging_native
from app.domains.lighting import service as lighting_service
from app.domains.rigging import power_tree
from app.domains.rigging.calc import WeightLoad
from app.domains.venues.models import VenuePowerOutlet


@dataclass(frozen=True)
class LoadRow:
    id: str
    kind: str
    label: str
    weight_kg: float | None
    power_w: float | None
    rigging_point_id: str | None
    power_node_id: str | None
    power_connector: str
    device_id: str | None = None


async def _fetcher(db: AsyncSession):
    from app.domains.audio.router import stockwire_product_fetcher

    return await stockwire_product_fetcher(db)


async def collect_loads(db: AsyncSession, job_id: UUID) -> list[LoadRow]:
    devices = await audio_service.list_devices(db, job_id)
    by_id = {str(device.id): device for device in devices}
    device_product = {str(d.id): d.stockwire_product_id for d in devices if d.stockwire_product_id}
    fetch = await _fetcher(db) if device_product else None
    physical = await resolve_device_physical(device_product, fetch)
    types = {str(t.id): t for t in await lighting_service.list_types(db, job_id)}

    def values(device_id) -> tuple[str, float | None, float | None]:
        device = by_id.get(str(device_id)) if device_id else None
        if device is None:
            return "", None, None
        phys = physical.get(str(device.id), {})
        weight = effective_value(phys.get("weight_kg"), device.weight_kg)[0]
        power = effective_value(phys.get("power_watts"), device.power_watts)[0]
        return device.name, weight, power

    rows: list[LoadRow] = []
    for fixture in await lighting_service.list_fixtures(db, job_id):
        name, weight, power = values(fixture.device_id)
        fixture_type = types.get(str(fixture.fixture_type_id)) if fixture.fixture_type_id else None
        if fixture_type is not None:
            weight = weight if weight is not None else fixture_type.weight_kg
            power = power if power is not None else fixture_type.power_watts
        rows.append(
            LoadRow(
                id=str(fixture.id),
                kind="fixture",
                label=name or f"Fixture {fixture.dmx_address or ''}".strip(),
                weight_kg=weight,
                power_w=power,
                rigging_point_id=str(fixture.rigging_point_id)
                if fixture.rigging_point_id
                else None,
                power_node_id=str(fixture.power_node_id) if fixture.power_node_id else None,
                power_connector=fixture.power_connector or "",
                device_id=str(fixture.device_id) if fixture.device_id else None,
            )
        )
    for element in await audio_service.list_plot_elements(db, job_id):
        if not element.linked_device_id:
            continue
        name, weight, power = values(element.linked_device_id)
        rows.append(
            LoadRow(
                id=str(element.id),
                kind="element",
                label=element.label or name or element.element_type,
                weight_kg=weight,
                power_w=power,
                rigging_point_id=str(element.rigging_point_id)
                if element.rigging_point_id
                else None,
                power_node_id=str(element.power_node_id) if element.power_node_id else None,
                power_connector=element.power_connector or "",
                device_id=str(element.linked_device_id),
            )
        )

    # A plain device (no fixture, no plot element standing for it) is a load of its own, so it can
    # be plugged into a node. Devices that already count through a fixture or an element are left
    # out so their watts are not counted twice. Only devices that draw power or are plugged show.
    covered = {r.device_id for r in rows if r.device_id}
    powered_by_node = {n.device_id for n in await list_nodes(db, job_id) if n.device_id}
    for device in devices:
        if str(device.id) in covered or device.id in powered_by_node:
            continue
        name, weight, power = values(device.id)
        if device.power_inlet == "none":
            power = None
        if (
            not power
            and not weight
            and device.power_node_id is None
            and device.rigging_point_id is None
        ):
            continue
        rows.append(
            LoadRow(
                id=str(device.id),
                kind="device",
                label=name or device.name,
                weight_kg=weight,
                power_w=power,
                rigging_point_id=str(device.rigging_point_id) if device.rigging_point_id else None,
                power_node_id=str(device.power_node_id) if device.power_node_id else None,
                power_connector=device.power_connector or "",
                device_id=str(device.id),
            )
        )
    return rows


def weight_loads(rows: list[LoadRow]) -> list[WeightLoad]:
    return [WeightLoad(r.label, r.weight_kg, r.rigging_point_id) for r in rows]


def to_tree_nodes(nodes: list, feeds: list | None = None) -> list[power_tree.Node]:
    feeds = feeds or []
    feeds_by_node: dict[str, list] = {}
    for f in feeds:
        feeds_by_node.setdefault(str(f.node_id), []).append(f)
    tree_nodes = []
    for n in nodes:
        node_feeds = []
        if n.parent_id:
            node_feeds.append(power_tree.Feed(str(n.parent_id), n.feed_connector, n.phase))
        for f in feeds_by_node.get(str(n.id), []):
            node_feeds.append(power_tree.Feed(str(f.parent_id), f.feed_connector, f.phase))
        tree_nodes.append(
            power_tree.Node(
                id=str(n.id),
                kind=n.kind,
                name=n.name or n.kind,
                feeds=tuple(node_feeds),
                feed_connector=n.feed_connector,
                phase=n.phase,
                outputs=tuple(
                    power_tree.Output(o["connector"], int(o["count"]), o.get("phase"))
                    for o in (n.outputs or [])
                ),
                rating_amps=n.rating_amps,
                active=n.active,
            )
        )
    return tree_nodes


def to_tree_loads(rows: list[LoadRow]) -> list[power_tree.Load]:
    from app.domains.rigging.power_tree import Load

    return [
        Load(
            id=r.id,
            label=r.label,
            node_id=r.power_node_id,
            connector=r.power_connector,
            watts=r.power_w,
            kind=r.kind,
        )
        for r in rows
    ]


async def list_points(db: AsyncSession, job_id: UUID):
    return await rigging_native.load_points(db, job_id)


async def list_nodes(db: AsyncSession, job_id: UUID):
    return await power_native.load_nodes(db, job_id)


async def get_point(db: AsyncSession, job_id: UUID, point_id: UUID):
    return await rigging_native.get_point(db, job_id, point_id)


async def get_node(db: AsyncSession, job_id: UUID, node_id: UUID):
    return await power_native.get_node(db, job_id, node_id)


async def list_feeds(db: AsyncSession, job_id: UUID):
    return await power_native.load_feeds(db, job_id)


async def get_outlet(db: AsyncSession, venue_id: UUID | None, outlet_id: UUID):
    if venue_id is None:
        return None
    outlet = await db.get(VenuePowerOutlet, outlet_id)
    return outlet if outlet is not None and outlet.venue_id == venue_id else None


async def venue_outlets(db: AsyncSession, venue_id: UUID | None) -> list[VenuePowerOutlet]:
    if venue_id is None:
        return []
    result = await db.execute(
        select(VenuePowerOutlet)
        .where(VenuePowerOutlet.venue_id == venue_id)
        .order_by(VenuePowerOutlet.name)
    )
    return list(result.scalars().all())


async def next_position(db: AsyncSession, model, job_id: UUID) -> int:
    count = await db.scalar(select(func.count(model.id)).where(model.job_id == job_id))
    return count or 0


async def save(db: AsyncSession, obj):
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj
