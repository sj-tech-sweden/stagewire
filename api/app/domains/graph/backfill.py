import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelListOutput,
    ChannelPatchPoint,
    OutputPatchPoint,
    StagePlotElement,
)
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.lighting.models import DmxStep, DmxUniverse, LightingFixture
from app.domains.rigging.models import PowerNode, PowerNodeFeed
from app.domains.video.models import VideoInputList

FAN_OUT = 64

CHANNEL_FIELDS = (
    "channel_number",
    "input_type",
    "connector",
    "device",
    "stand_type",
    "instrument_group",
    "performer_name",
    "wireless_pack",
    "wireless_frequency",
    "phantom_power",
    "stereo",
    "stereo_channel",
    "color_code",
    "stockwire_asset_id",
    "stand_product_id",
    "stand_product_name",
)
OUTPUT_FIELDS = ("mode", "connector", "color_code")


@dataclass
class BackfillResult:
    devices: int = 0
    edges: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)


def _domain_for(device: AudioDevice) -> str:
    if device.fixture_type:
        return "lighting"
    if device.video_list_id or device.throw_ratio_min or device.sensor_width_mm:
        return "video"
    return "audio"


def _group_ports(device: AudioDevice, signal: str) -> list[dict]:
    ports: list[dict] = []
    seen: set[str] = set()
    for group in device.ports or []:
        direction = group.get("direction") or "in"
        connector = (group.get("connector") or "").lower()
        base = f"{direction}-{connector or 'x'}"
        pid, n = base, 1
        while pid in seen:
            n += 1
            pid = f"{base}-{n}"
        seen.add(pid)
        ports.append(
            {
                "id": pid,
                "direction": direction,
                "signal": signal,
                "connector": connector or None,
                "channels": group.get("count") or None,
                "label": "",
            }
        )
    return ports


class Backfill:
    def __init__(self, db: AsyncSession, job_id: uuid.UUID) -> None:
        self.db = db
        self.job_id = job_id
        self.devices: dict[str, GraphDevice] = {}
        self.edge_refs: set[str] = set()
        self.result = BackfillResult()

    async def load_existing(self) -> None:
        for device in (
            await self.db.scalars(select(GraphDevice).where(GraphDevice.job_id == self.job_id))
        ).all():
            if device.legacy_ref:
                self.devices[device.legacy_ref] = device
        for edge in (
            await self.db.scalars(
                select(ConnectionEdge).where(ConnectionEdge.job_id == self.job_id)
            )
        ).all():
            ref = (edge.attributes or {}).get("legacy_ref")
            if ref:
                self.edge_refs.add(ref)

    def device(self, ref: str, **fields) -> GraphDevice:
        existing = self.devices.get(ref)
        if existing is not None:
            missing = {
                k: v
                for k, v in (fields.get("attributes") or {}).items()
                if k not in existing.attributes
            }
            if missing:
                existing.attributes = {**existing.attributes, **missing}
            self.result.skipped += 1
            return existing
        device = GraphDevice(id=uuid.uuid4(), job_id=self.job_id, legacy_ref=ref, **fields)
        device.attributes = fields.get("attributes") or {}
        device.ports = fields.get("ports") or []
        self.db.add(device)
        self.devices[ref] = device
        self.result.devices += 1
        return device

    @staticmethod
    def port(device: GraphDevice, direction: str, signal: str, connector: str = "") -> str:
        wanted = connector.lower()
        candidates = [
            p
            for p in device.ports
            if p["direction"] == direction and p.get("signal") in (None, signal)
        ]
        for p in candidates:
            if wanted and p.get("connector") == wanted:
                return p["id"]
        if candidates:
            return candidates[0]["id"]
        new = {
            "id": f"{direction}-{signal}",
            "direction": direction,
            "signal": signal,
            "connector": None,
        }
        if direction == "out":
            new["max_connections"] = FAN_OUT
        device.ports = [*device.ports, new]
        return new["id"]

    @classmethod
    def named_port(
        cls, device: GraphDevice, direction: str, signal: str, name: str, connector: str = ""
    ) -> str:
        if not name:
            return cls.port(device, direction, signal, connector)
        for p in device.ports:
            if p["id"] == name and p["direction"] == direction:
                return name
        pid = name if all(p["id"] != name for p in device.ports) else f"{name}-{direction}"
        new = {
            "id": pid,
            "direction": direction,
            "signal": signal,
            "connector": connector.lower() or None,
        }
        if direction == "out":
            new["max_connections"] = FAN_OUT
        device.ports = [*device.ports, new]
        return pid

    def edge(
        self,
        ref: str,
        signal: str,
        src: GraphDevice,
        sport: str,
        dst: GraphDevice,
        dport: str,
        *,
        phase: str | None = None,
        attributes: dict | None = None,
    ) -> None:
        if ref in self.edge_refs:
            self.result.skipped += 1
            return
        self.edge_refs.add(ref)
        self.db.add(
            ConnectionEdge(
                id=uuid.uuid4(),
                job_id=self.job_id,
                signal=signal,
                src_device_id=src.id,
                src_port=sport,
                dst_device_id=dst.id,
                dst_port=dport,
                channels=1,
                phase=phase if phase in ("L1", "L2", "L3") else None,
                attributes={"legacy_ref": ref, **(attributes or {})},
            )
        )
        self.result.edges += 1

    async def audio_devices(self) -> None:
        rows = await self.db.scalars(select(AudioDevice).where(AudioDevice.job_id == self.job_id))
        for row in rows.all():
            domain = _domain_for(row)
            signal = {"lighting": "dmx", "video": "video"}.get(domain, "audio")
            attributes = {
                k: v
                for k, v in {
                    "device_type": row.device_type,
                    "weight_kg": row.weight_kg,
                    "power_w": row.power_watts,
                    "input_override": row.input_override,
                    "output_override": row.output_override,
                    "fixture_type": row.fixture_type,
                    "channel_mode": row.channel_mode,
                    "footprint_channels": row.footprint_channels,
                    "default_gel": row.default_gel,
                }.items()
                if v not in (None, "")
            }
            self.device(
                f"audio_devices:{row.id}",
                domain=domain,
                kind=row.device_type or "other",
                name=row.name or row.device_type or "Device",
                notes=row.notes or "",
                position=row.position,
                attributes=attributes,
                ports=_group_ports(row, signal),
                stockwire_product_id=row.stockwire_product_id,
                stockwire_product_name=row.stockwire_product_name,
            )

    async def channel_lists(self) -> None:
        lists = (
            await self.db.scalars(select(ChannelList).where(ChannelList.job_id == self.job_id))
        ).all()
        for row in lists:
            self.device(
                f"audio_channel_lists:{row.id}",
                domain="audio",
                kind="channel_list",
                name=row.name,
                position=row.position,
                attributes={
                    k: v
                    for k, v in {
                        "mixer_product_id": row.mixer_product_id,
                        "mixer_product_name": row.mixer_product_name,
                        "mixer_inputs": row.mixer_inputs,
                        "mixer_buses": row.mixer_buses,
                    }.items()
                    if v is not None
                },
                ports=[],
                stockwire_product_id=row.mixer_product_id,
                stockwire_product_name=row.mixer_product_name,
            )

    def _list_id(self, legacy_list_id: uuid.UUID) -> str:
        container = self.devices.get(f"audio_channel_lists:{legacy_list_id}")
        return str(container.id) if container is not None else str(legacy_list_id)

    async def channels(self) -> None:
        channels = (
            await self.db.scalars(
                select(AudioChannelPatch)
                .join(ChannelList, AudioChannelPatch.channel_list_id == ChannelList.id)
                .where(ChannelList.job_id == self.job_id)
            )
        ).all()
        points = (
            await self.db.scalars(
                select(ChannelPatchPoint)
                .where(ChannelPatchPoint.channel_id.in_([c.id for c in channels]))
                .order_by(ChannelPatchPoint.position)
            )
        ).all()
        by_channel: dict[uuid.UUID, list[ChannelPatchPoint]] = {}
        for point in points:
            by_channel.setdefault(point.channel_id, []).append(point)
        for channel in channels:
            node = self.device(
                f"audio_channel_patches:{channel.id}",
                domain="audio",
                kind="channel",
                name=channel.source_label or f"Ch {channel.channel_number}",
                position=channel.channel_number,
                notes=channel.notes or "",
                attributes={
                    "list_id": self._list_id(channel.channel_list_id),
                    "channel_list_id": str(channel.channel_list_id),
                    **{
                        field: getattr(channel, field)
                        for field in CHANNEL_FIELDS
                        if getattr(channel, field) is not None
                    },
                },
                ports=[{"id": "out", "direction": "out", "signal": "audio"}],
                stockwire_product_id=channel.stockwire_product_id,
                stockwire_product_name=channel.stockwire_product_name,
            )
            prev, prev_port = node, "out"
            for point in by_channel.get(channel.id, []):
                target = self.devices.get(f"audio_devices:{point.device_id}")
                if target is None:
                    self.result.notes.append(f"patch point {point.id}: device missing")
                    continue
                self.edge(
                    f"channel_patch_points:{point.id}",
                    "audio",
                    prev,
                    prev_port,
                    target,
                    self.port(target, "in", "audio", point.connector),
                    attributes={
                        "channel_number": channel.channel_number,
                        "patch_label": point.patch_label,
                    },
                )
                prev, prev_port = target, self.port(target, "out", "audio", point.connector)

    async def audio_outputs(self) -> None:
        outputs = (
            await self.db.scalars(
                select(ChannelListOutput)
                .join(ChannelList, ChannelListOutput.channel_list_id == ChannelList.id)
                .where(ChannelList.job_id == self.job_id)
            )
        ).all()
        points = (
            await self.db.scalars(
                select(OutputPatchPoint)
                .where(OutputPatchPoint.output_id.in_([o.id for o in outputs]))
                .order_by(OutputPatchPoint.position)
            )
        ).all()
        by_output: dict[uuid.UUID, list[OutputPatchPoint]] = {}
        for point in points:
            if point.device_id:
                by_output.setdefault(point.output_id, []).append(point)
        for output in outputs:
            bus = self.device(
                f"channel_list_outputs:{output.id}",
                domain="audio",
                kind="output",
                name=output.name,
                notes=output.notes or "",
                position=output.position,
                attributes={
                    "list_id": self._list_id(output.channel_list_id),
                    "channel_list_id": str(output.channel_list_id),
                    **{
                        field: getattr(output, field)
                        for field in OUTPUT_FIELDS
                        if getattr(output, field) is not None
                    },
                },
                ports=[
                    {"id": "in", "direction": "in", "signal": "audio"},
                    {
                        "id": "out",
                        "direction": "out",
                        "signal": "audio",
                        "max_connections": FAN_OUT,
                    },
                ],
            )
            chain = by_output.get(output.id, [])
            by_id = {p.id: p for p in chain}
            console = self.devices.get(f"audio_devices:{chain[0].device_id}") if chain else None
            if console is not None:
                self.edge(
                    f"channel_list_outputs:{output.id}",
                    "audio",
                    console,
                    self.port(console, "out", "audio", output.connector or ""),
                    bus,
                    "in",
                    attributes={"connector": output.connector},
                )
            for index, point in enumerate(chain):
                if index == 0:
                    continue
                parent = by_id.get(point.parent_id) if point.parent_id else chain[index - 1]
                target = self.devices.get(f"audio_devices:{point.device_id}")
                if parent is None or target is None or parent.device_id == point.device_id:
                    continue
                src = (
                    bus
                    if parent is chain[0]
                    else self.devices.get(f"audio_devices:{parent.device_id}")
                )
                if src is None:
                    continue
                self.edge(
                    f"output_patch_points:{point.id}",
                    "audio",
                    src,
                    "out" if src is bus else self.port(src, "out", "audio", point.connector),
                    target,
                    self.port(target, "in", "audio", point.connector),
                    attributes={
                        "output_id": str(output.id),
                        "patch_label": point.patch_label,
                        "bus_connector": point.bus_connector,
                        "parallel": point.parallel,
                    },
                )

    async def video(self) -> None:
        lists = (
            await self.db.scalars(
                select(VideoInputList).where(VideoInputList.job_id == self.job_id)
            )
        ).all()
        for vlist in lists:
            for vin in vlist.inputs:
                source = self.device(
                    f"video_inputs:{vin.id}",
                    domain="video",
                    kind="video_input",
                    name=vin.source_label or f"Input {vin.input_number}",
                    notes=vin.notes or "",
                    position=vin.input_number,
                    attributes={
                        "input_number": vin.input_number,
                        "source_type": vin.source_type,
                        "list_id": str(vlist.id),
                    },
                    ports=[
                        {
                            "id": "out",
                            "direction": "out",
                            "signal": "video",
                            "connector": (vin.connector or "").lower() or None,
                        }
                    ],
                )
                prev = source
                for point in vin.patch_points:
                    target = self.devices.get(f"audio_devices:{point.device_id}")
                    if target is None or target is prev:
                        continue
                    self.edge(
                        f"video_patch_points:{point.id}",
                        "video",
                        prev,
                        "out"
                        if prev is source
                        else self.named_port(
                            prev, "out", "video", point.source_port, point.connector
                        ),
                        target,
                        self.named_port(target, "in", "video", point.input_port, point.connector),
                        attributes={
                            "patch_label": point.patch_label,
                            "input_number": vin.input_number,
                        },
                    )
                    prev = target
            for vout in vlist.outputs:
                self._video_output(vlist, vout)

    def _video_output(self, vlist: VideoInputList, vout) -> None:
        dest_ref = f"video_outputs:{vout.id}"
        points = [p for p in vout.patch_points if p.device_id]
        leaves = {p.id for p in points} - {p.parent_id for p in points if p.parent_id}
        dest = self.device(
            dest_ref,
            domain="video",
            kind="video_destination",
            name=vout.destination_label or vout.name or f"Output {vout.output_number}",
            notes=vout.notes or "",
            position=vout.output_number,
            attributes={"output_number": vout.output_number, "list_id": str(vlist.id)},
            ports=[
                {
                    "id": "in",
                    "direction": "in",
                    "signal": "video",
                    "connector": (vout.connector or "").lower() or None,
                    "channels": max(1, len(leaves)),
                }
            ],
        )
        by_id = {p.id: p for p in points}
        for point in points:
            target = self.devices.get(f"audio_devices:{point.device_id}")
            parent = by_id.get(point.parent_id) if point.parent_id else None
            if parent is not None and target is not None and parent.device_id != point.device_id:
                src = self.devices.get(f"audio_devices:{parent.device_id}")
                if src is not None:
                    self.edge(
                        f"video_output_patch_points:{point.id}",
                        "video",
                        src,
                        self.named_port(src, "out", "video", point.source_port, point.connector),
                        target,
                        self.named_port(target, "in", "video", point.input_port, point.connector),
                        attributes={"patch_label": point.patch_label, "output_id": str(vout.id)},
                    )
            if point.id in leaves and target is not None:
                self.edge(
                    f"video_outputs.dest:{point.id}",
                    "video",
                    target,
                    self.port(target, "out", "video", point.connector),
                    dest,
                    "in",
                    attributes={"output_id": str(vout.id)},
                )

    async def plot_links(self) -> None:
        """Point each stage plot element at the graph node its legacy links resolve to.

        An element can carry several legacy links; one graph node is kept, in this priority:
        channel, video input, output point, device, patch point.
        """
        elements = (
            await self.db.scalars(
                select(StagePlotElement).where(StagePlotElement.job_id == self.job_id)
            )
        ).all()
        point_device = {
            p.id: p.device_id
            for p in (await self.db.scalars(select(ChannelPatchPoint))).all()
            if p.device_id
        }
        out_device = {
            p.id: p.device_id
            for p in (await self.db.scalars(select(OutputPatchPoint))).all()
            if p.device_id
        }
        for el in elements:
            if el.graph_device_id is not None:
                continue
            candidates = [
                ("channel", f"audio_channel_patches:{el.linked_channel_id}")
                if el.linked_channel_id
                else None,
                ("video_input", f"video_inputs:{el.linked_video_input_id}")
                if el.linked_video_input_id
                else None,
                ("output_point", f"audio_devices:{out_device.get(el.linked_output_point_id)}")
                if el.linked_output_point_id in out_device
                else None,
                ("device", f"audio_devices:{el.linked_device_id}") if el.linked_device_id else None,
                ("patch_point", f"audio_devices:{point_device.get(el.linked_patch_point_id)}")
                if el.linked_patch_point_id in point_device
                else None,
            ]
            candidates = [c for c in candidates if c]
            if len(candidates) > 1:
                self.result.notes.append(
                    f"plot element {el.id} has {len(candidates)} links; kept {candidates[0][0]}"
                )
            for role, ref in candidates:
                node = self.devices.get(ref)
                if node is not None:
                    el.graph_device_id, el.graph_link_role = node.id, role
                    break

    async def lighting(self) -> None:
        fixtures = (
            await self.db.scalars(
                select(LightingFixture).where(LightingFixture.job_id == self.job_id)
            )
        ).all()
        fixture_nodes: dict[uuid.UUID, GraphDevice] = {}
        for fx in fixtures:
            dmx = {
                "universe": fx.universe,
                "dmx_address": fx.dmx_address,
                "fixture_type": fx.fixture_type,
                "channel_mode": fx.channel_mode,
                "footprint": fx.footprint,
                "location": fx.location,
                "gel": fx.gel,
                "purpose": fx.purpose,
            }
            dmx = {k: v for k, v in dmx.items() if v not in (None, "")}
            linked = self.devices.get(f"audio_devices:{fx.device_id}") if fx.device_id else None
            if linked is not None:
                linked.attributes = {**linked.attributes, **dmx}
                linked.domain = "lighting"
                fixture_nodes[fx.id] = linked
                continue
            fixture_nodes[fx.id] = self.device(
                f"lighting_fixtures:{fx.id}",
                domain="lighting",
                kind="fixture",
                name=fx.purpose or fx.fixture_type or "Fixture",
                notes=fx.notes or "",
                position=fx.position,
                attributes=dmx,
                ports=[],
            )
        steps = (
            await self.db.execute(
                select(DmxStep, DmxUniverse)
                .join(DmxUniverse, DmxStep.universe_id == DmxUniverse.id)
                .where(DmxUniverse.job_id == self.job_id)
                .order_by(DmxStep.position)
            )
        ).all()
        node_of: dict[uuid.UUID, GraphDevice] = {}
        for step, _ in steps:
            if step.fixture_id and step.fixture_id in fixture_nodes:
                node_of[step.id] = fixture_nodes[step.fixture_id]
            elif step.device_id:
                node_of[step.id] = self.devices.get(f"audio_devices:{step.device_id}")
        for step, universe in steps:
            node = node_of.get(step.id)
            if node is None:
                continue
            if step.parent_id and step.parent_id in node_of:
                parent = node_of[step.parent_id]
            elif universe.source_device_id:
                parent = self.devices.get(f"audio_devices:{universe.source_device_id}")
            else:
                continue
            if parent is None:
                continue
            out_id = self.port(parent, "out", "dmx", step.connector)
            self.edge(
                f"dmx_steps:{step.id}",
                "dmx",
                parent,
                out_id,
                node,
                self.port(node, "in", "dmx", step.connector),
                attributes={"universe": universe.number},
            )
        for fx in fixtures:
            if fx.power_node_id:
                node = fixture_nodes[fx.id]
                src = self.devices.get(f"power_nodes:{fx.power_node_id}")
                if src is not None:
                    self.edge(
                        f"lighting_fixtures.power:{fx.id}",
                        "power",
                        src,
                        self.port(src, "out", "power", fx.power_connector),
                        node,
                        self.port(node, "in", "power", fx.power_connector),
                        attributes={"connector": fx.power_connector},
                    )

    async def power(self) -> None:
        nodes = (
            await self.db.scalars(select(PowerNode).where(PowerNode.job_id == self.job_id))
        ).all()
        for node in nodes:
            attributes = {
                k: v
                for k, v in {
                    "rating_amps": node.rating_amps,
                    "active": node.active,
                    "outputs": node.outputs,
                    "venue_outlet_id": str(node.venue_outlet_id) if node.venue_outlet_id else None,
                }.items()
                if v not in (None, [])
            }
            linked = self.devices.get(f"audio_devices:{node.device_id}") if node.device_id else None
            if linked is not None:
                linked.attributes = {**linked.attributes, **attributes}
                self.devices[f"power_nodes:{node.id}"] = linked
                continue
            self.device(
                f"power_nodes:{node.id}",
                domain="power",
                kind=node.kind,
                name=node.name or node.kind,
                notes=node.notes or "",
                position=node.position,
                attributes=attributes,
                ports=[],
                canvas_x_cm=node.x_cm,
                canvas_y_cm=node.y_cm,
            )
        for node in nodes:
            if node.parent_id:
                self._power_edge(
                    f"power_nodes:{node.id}",
                    node.parent_id,
                    node.id,
                    node.feed_connector,
                    node.phase,
                )
        feeds = (
            await self.db.scalars(select(PowerNodeFeed).where(PowerNodeFeed.job_id == self.job_id))
        ).all()
        for feed in feeds:
            self._power_edge(
                f"power_node_feeds:{feed.id}",
                feed.parent_id,
                feed.node_id,
                feed.feed_connector,
                feed.phase,
            )

    def _power_edge(
        self, ref: str, parent_id: uuid.UUID, node_id: uuid.UUID, connector: str, phase: str | None
    ) -> None:
        parent = self.devices.get(f"power_nodes:{parent_id}")
        node = self.devices.get(f"power_nodes:{node_id}")
        if parent is None or node is None:
            return
        self.edge(
            ref,
            "power",
            parent,
            self.port(parent, "out", "power", connector),
            node,
            self.port(node, "in", "power", connector),
            phase=phase,
            attributes={"connector": connector},
        )


async def backfill_job(db: AsyncSession, job_id: uuid.UUID) -> BackfillResult:
    """Copy a job's legacy audio/lighting/power rows into the unified graph.

    Idempotent: rows and edges carry a ``legacy_ref`` so a second run only adds what is new.
    Audio output chains hang off a bus node fed by the first patch point (the console).
    """
    builder = Backfill(db, job_id)
    await builder.load_existing()
    await builder.audio_devices()
    await builder.power()
    await builder.channel_lists()
    await builder.channels()
    await builder.audio_outputs()
    await builder.video()
    await builder.lighting()
    await builder.plot_links()
    await db.commit()
    return builder.result
