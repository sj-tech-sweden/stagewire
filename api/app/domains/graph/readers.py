import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.wwb import normalize_wireless_attributes
from app.domains.graph.models import GraphDevice

CHANNEL_DEFAULTS = {
    "channel_number": 0,
    "input_type": None,
    "connector": None,
    "device": None,
    "stand_type": "",
    "instrument_group": "other",
    "performer_name": None,
    "wireless_pack": None,
    "wireless_frequency_mhz": None,
    "wireless_group": None,
    "wireless_channel": None,
    "phantom_power": False,
    "stereo": False,
    "stereo_channel": None,
    "color_code": None,
}
OUTPUT_DEFAULTS = {"mode": "mono", "connector": None, "color_code": None}


def channel_view(device: GraphDevice) -> SimpleNamespace:
    attrs = {**CHANNEL_DEFAULTS, **(device.attributes or {})}
    # fold the structured MHz (or a legacy free-text ``wireless_frequency`` string) into
    # the read model so unmigrated rows still expose ``wireless_frequency_mhz``
    attrs = {**attrs, **normalize_wireless_attributes(attrs)}
    return SimpleNamespace(
        id=device.id,
        source_label=attrs.get("source_label", device.name),
        notes=device.notes or "",
        **{key: attrs[key] for key in CHANNEL_DEFAULTS},
    )


def output_view(device: GraphDevice) -> SimpleNamespace:
    attrs = {**OUTPUT_DEFAULTS, **(device.attributes or {})}
    return SimpleNamespace(
        id=device.id,
        name=device.name,
        position=device.position,
        notes=device.notes or "",
        **{key: attrs[key] for key in OUTPUT_DEFAULTS},
    )


def list_view(device: GraphDevice) -> SimpleNamespace:
    attrs = device.attributes or {}
    return SimpleNamespace(
        id=device.id,
        job_id=device.job_id,
        name=device.name,
        position=device.position,
        mixer_product_id=attrs.get("mixer_product_id"),
        mixer_product_name=attrs.get("mixer_product_name"),
        mixer_inputs=attrs.get("mixer_inputs"),
        mixer_buses=attrs.get("mixer_buses"),
    )


async def load_channel_list(
    db: AsyncSession,
    job_id: uuid.UUID | None = None,
    list_id: uuid.UUID | None = None,
    *,
    venue_id: uuid.UUID | None = None,
) -> tuple[SimpleNamespace, list[SimpleNamespace], list[SimpleNamespace]] | None:
    """A channel list as the console exporters expect it: (list, channels, outputs).

    Scoped to a job (``job_id``) or a venue (``venue_id``) — exactly one must be given, since
    a channel list lives in either a job graph or a venue Standard Base Rig graph.
    """
    if (job_id is None) == (venue_id is None):
        raise ValueError("load_channel_list requires exactly one of job_id / venue_id")
    container = await db.get(GraphDevice, list_id)
    if container is None or container.kind != "channel_list":
        return None
    if job_id is not None and container.job_id != job_id:
        return None
    if venue_id is not None and container.venue_id != venue_id:
        return None
    scope = GraphDevice.job_id == job_id if job_id is not None else GraphDevice.venue_id == venue_id
    rows = (
        await db.scalars(
            select(GraphDevice).where(
                scope,
                GraphDevice.domain == "audio",
                GraphDevice.kind.in_(("channel", "output")),
            )
        )
    ).all()
    mine = [r for r in rows if (r.attributes or {}).get("list_id") == str(list_id)]
    channels = sorted(
        (channel_view(r) for r in mine if r.kind == "channel"), key=lambda c: c.channel_number
    )
    outputs = sorted((output_view(r) for r in mine if r.kind == "output"), key=lambda o: o.position)
    return list_view(container), channels, outputs
