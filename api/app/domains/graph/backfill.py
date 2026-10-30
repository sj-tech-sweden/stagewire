import copy
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

ELEMENT_FIELDS = (
    "element_type",
    "width_cm",
    "height_cm",
    "image_url",
    "coverage_angle_h",
    "coverage_distance_m",
    "focal_mm",
    "power_connector",
)
# legacy link column -> role of the ``link`` edge from the element node to its target
ELEMENT_LINKS = {
    "linked_channel_id": "channel",
    "linked_device_id": "device",
    "linked_patch_point_id": "patch_point",
    "linked_output_point_id": "output_point",
    "linked_video_input_id": "video_input",
    "linked_lens_device_id": "lens",
    "power_node_id": "power_node",
}
# Rows whose legacy editors the graph mirrors both ways: legacy-owned fields keep flowing into
# the graph even when the twin was edited there, because graph edits are mirrored back at once.
OWNED_ATTRS: dict[str, set[str]] = {
    "audio_channel_patches": {*CHANNEL_FIELDS, "list_id", "channel_list_id"},
    "audio_channel_lists": {
        "mixer_product_id",
        "mixer_product_name",
        "mixer_inputs",
        "mixer_buses",
    },
    "channel_list_outputs": {*OUTPUT_FIELDS, "list_id", "channel_list_id"},
    "stage_plot_elements": {*ELEMENT_FIELDS, "rigging_point_id", "label"},
    "audio_devices": {
        "device_type",
        "weight_kg",
        "power_w",
        "input_override",
        "output_override",
        "fixture_type",
        "channel_mode",
        "footprint_channels",
        "default_gel",
    },
}
OWNED_DEVICE_FIELDS = (
    "name",
    "notes",
    "position",
    "stockwire_product_id",
    "stockwire_product_name",
)
MIRRORED_EDGE_TABLES = {
    "channel_patch_points",
    "output_patch_points",
    "channel_list_outputs",
    "stage_plot_elements.link",
}
CANVAS_OWNED_TABLES = {"stage_plot_elements"}


def _table(ref: str) -> str:
    return ref.partition(":")[0]


@dataclass
class BackfillResult:
    devices: int = 0
    edges: int = 0
    skipped: int = 0
    updated: int = 0
    removed: int = 0
    notes: list[str] = field(default_factory=list)
    changed_devices: list[uuid.UUID] = field(default_factory=list)
    changed_edges: list[uuid.UUID] = field(default_factory=list)
    removed_devices: list[tuple[uuid.UUID, list[uuid.UUID]]] = field(default_factory=list)
    removed_edges: list[uuid.UUID] = field(default_factory=list)


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


def _video_point_attrs(point, chain_root: GraphDevice) -> dict:
    return {
        "chain": str(chain_root.id),
        "point_id": str(point.id),
        "position": point.position,
        "connector": point.connector or "",
        "patch_label": point.patch_label or "",
        "notes": point.notes or "",
        "source_port": point.source_port or "",
        "input_port": point.input_port or "",
        "parent_id": str(point.parent_id) if getattr(point, "parent_id", None) else None,
    }


def _point_attrs(point, chain_root: GraphDevice, *, bus_connector: bool = False) -> dict:
    attrs = {
        "chain": str(chain_root.id),
        "point_id": str(point.id),
        "position": point.position,
        "point_type": getattr(point, "point_type", None),
        "connector": point.connector or "",
        "patch_label": point.patch_label or "",
        "notes": point.notes or "",
        "parent_id": str(point.parent_id) if getattr(point, "parent_id", None) else None,
    }
    if bus_connector:
        attrs["bus_connector"] = getattr(point, "bus_connector", None) or ""
    return attrs


class Backfill:
    def __init__(self, db: AsyncSession, job_id: uuid.UUID) -> None:
        self.db = db
        self.job_id = job_id
        self.devices: dict[str, GraphDevice] = {}
        self.edge_refs: set[str] = set()
        self.edge_rows: dict[str, ConnectionEdge] = {}
        self.loaded_devices: set[str] = set()
        self.loaded_edges: set[str] = set()
        self.loaded_revisions: dict[uuid.UUID, int] = {}
        self.new_edges: list[ConnectionEdge] = []
        self.edge_updates: list[tuple[ConnectionEdge, dict]] = []
        self.seen_devices: set[str] = set()
        self.seen_edges: set[str] = set()
        self.result = BackfillResult()

    async def load_existing(self) -> None:
        for device in (
            await self.db.scalars(select(GraphDevice).where(GraphDevice.job_id == self.job_id))
        ).all():
            if device.legacy_ref:
                self.devices[device.legacy_ref] = device
                self.loaded_devices.add(device.legacy_ref)
                self.loaded_revisions[device.id] = device.revision
        for edge in (
            await self.db.scalars(
                select(ConnectionEdge).where(ConnectionEdge.job_id == self.job_id)
            )
        ).all():
            ref = (edge.attributes or {}).get("legacy_ref")
            if ref:
                self.edge_refs.add(ref)
                self.edge_rows[ref] = edge
                self.loaded_edges.add(ref)
                self.loaded_revisions[edge.id] = edge.revision

    def device(self, ref: str, **fields) -> GraphDevice:
        self.seen_devices.add(ref)
        existing = self.devices.get(ref)
        if existing is not None:
            if not existing.graph_edited:
                for key, value in fields.items():
                    if key in ("attributes", "ports"):
                        value = (
                            copy.deepcopy(value) if value else ({} if key == "attributes" else [])
                        )
                    setattr(existing, key, value)
            elif _table(ref) in OWNED_ATTRS:
                table = _table(ref)
                for key in OWNED_DEVICE_FIELDS:
                    if key in fields:
                        setattr(existing, key, fields[key])
                attrs = {
                    k: v for k, v in existing.attributes.items() if k not in OWNED_ATTRS[table]
                }
                owned_new = fields.get("attributes") or {}
                attrs.update({k: v for k, v in owned_new.items() if k in OWNED_ATTRS[table]})
                existing.attributes = attrs
                if table in CANVAS_OWNED_TABLES:
                    for key in ("canvas_x_cm", "canvas_y_cm", "canvas_rotation"):
                        if key in fields:
                            setattr(existing, key, fields[key])
                if table == "audio_devices":
                    existing.kind, existing.domain = fields["kind"], fields["domain"]
                    existing.ports = copy.deepcopy(fields.get("ports") or [])
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
        self.seen_edges.add(ref)
        if ref in self.edge_refs:
            existing = self.edge_rows.get(ref)
            if existing is not None and (
                not existing.graph_edited or _table(ref) in MIRRORED_EDGE_TABLES
            ):
                values = {
                    "signal": signal,
                    "src_device_id": src.id,
                    "src_port": sport,
                    "dst_device_id": dst.id,
                    "dst_port": dport,
                    "attributes": {"legacy_ref": ref, **(attributes or {})},
                }
                if not existing.graph_edited:
                    values["phase"] = phase if phase in ("L1", "L2", "L3") else None
                self.edge_updates.append((existing, values))
            self.result.skipped += 1
            return
        self.edge_refs.add(ref)
        self.new_edges.append(
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
                        **_point_attrs(point, node),
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
                    attributes={
                        "connector": output.connector,
                        "first_point": _point_attrs(chain[0], bus, bus_connector=True),
                        "chain": str(bus.id),
                        "position": chain[0].position,
                    },
                )
            for index, point in enumerate(chain):
                if index == 0:
                    continue
                parent = by_id.get(point.parent_id) if point.parent_id else chain[index - 1]
                target = self.devices.get(f"audio_devices:{point.device_id}")
                if parent is None or target is None:
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
                        "parallel": point.parallel,
                        **_point_attrs(point, bus, bus_connector=True),
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
                        "source_label": vin.source_label or "",
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
                            "input_number": vin.input_number,
                            **_video_point_attrs(point, source),
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
            attributes={
                "output_number": vout.output_number,
                "name": vout.name or "",
                "destination_label": vout.destination_label or "",
                "list_id": str(vlist.id),
            },
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
                        attributes={
                            "output_id": str(vout.id),
                            **_video_point_attrs(point, dest),
                        },
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

    async def write_edges(self) -> None:
        """Insert devices first; nothing in the ORM orders edge inserts after them."""
        await self.db.flush()
        for edge, values in self.edge_updates:
            for key, value in values.items():
                if key == "attributes" and edge.graph_edited:
                    value = {**edge.attributes, **value}
                setattr(edge, key, value)
        self.db.add_all(self.new_edges)
        await self.db.flush()
        for edge in self.new_edges:
            self.edge_rows[edge.attributes["legacy_ref"]] = edge

    async def prune(self) -> None:
        """Remove untouched graph rows whose legacy source no longer exists."""
        gone_edges = [
            self.edge_rows[ref]
            for ref in self.loaded_edges - self.seen_edges
            if not self.edge_rows[ref].graph_edited
        ]
        gone_devices = {
            self.devices[ref].id: self.devices[ref]
            for ref in self.loaded_devices - self.seen_devices
            if ref in self.devices and not self.devices[ref].graph_edited
        }
        if not gone_edges and not gone_devices:
            return
        doomed = {e.id: e for e in gone_edges}
        for edge in (
            await self.db.scalars(
                select(ConnectionEdge).where(ConnectionEdge.job_id == self.job_id)
            )
        ).all():
            if edge.src_device_id in gone_devices or edge.dst_device_id in gone_devices:
                doomed[edge.id] = edge
        for edge in doomed.values():
            await self.db.delete(edge)
        await self.db.flush()
        for device_id, device in gone_devices.items():
            touching = [
                e.id for e in doomed.values() if device_id in (e.src_device_id, e.dst_device_id)
            ]
            self.result.removed_devices.append((device_id, touching))
            await self.db.delete(device)
        self.result.removed_edges = [
            e.id
            for e in doomed.values()
            if e.src_device_id not in gone_devices and e.dst_device_id not in gone_devices
        ]
        self.result.removed = len(doomed) + len(gone_devices)

    async def plot_elements(self) -> None:
        """Stage plot elements become ``plot_element`` nodes; their links become ``link`` edges."""
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
            node = self.device(
                f"stage_plot_elements:{el.id}",
                domain="other",
                kind="plot_element",
                name=el.label or el.element_type,
                position=0,
                attributes={
                    **{
                        key: getattr(el, key)
                        for key in ELEMENT_FIELDS
                        if getattr(el, key) is not None
                    },
                    "label": el.label or "",
                    **(
                        {"rigging_point_id": str(el.rigging_point_id)}
                        if el.rigging_point_id
                        else {}
                    ),
                },
                ports=[],
                canvas_x_cm=el.position_x,
                canvas_y_cm=el.position_y,
                canvas_rotation=el.rotation,
            )
            for column, role in ELEMENT_LINKS.items():
                legacy_id = getattr(el, column)
                if not legacy_id:
                    continue
                if role == "patch_point":
                    target_ref = f"audio_devices:{point_device.get(legacy_id)}"
                elif role == "output_point":
                    target_ref = f"audio_devices:{out_device.get(legacy_id)}"
                else:
                    table = {
                        "channel": "audio_channel_patches",
                        "video_input": "video_inputs",
                        "power_node": "power_nodes",
                    }.get(role, "audio_devices")
                    target_ref = f"{table}:{legacy_id}"
                target = self.devices.get(target_ref) if target_ref in self.seen_devices else None
                if target is None and role == "power_node":
                    target = self.devices.get(target_ref)
                if target is None:
                    continue
                self.edge(
                    f"stage_plot_elements.link:{el.id}:{role}",
                    "link",
                    node,
                    "link",
                    target,
                    role,
                    attributes={"role": role, "legacy_target": str(legacy_id)},
                )

    async def plot_links(self) -> None:
        """Point each stage plot element at its graph nodes.

        Recomputed on every sync while the plot editor still writes the legacy links. An element
        has up to two graph links: ``graph_device_id`` (its device, which places it on the plot)
        and a source link (``graph_source_id`` + role) for its cable, chosen by priority:
        channel, video input, output point, patch point.
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

        def node(ref: str):
            return self.devices.get(ref) if ref in self.seen_devices else None

        for el in elements:
            device = node(f"audio_devices:{el.linked_device_id}") if el.linked_device_id else None
            el.graph_device_id = device.id if device else None
            el.graph_link_role = None
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
                ("patch_point", f"audio_devices:{point_device.get(el.linked_patch_point_id)}")
                if el.linked_patch_point_id in point_device
                else None,
            ]
            el.graph_source_id, el.graph_source_role = None, None
            for role, ref in (c for c in candidates if c):
                source = node(ref)
                if source is not None:
                    el.graph_source_id, el.graph_source_role = source.id, role
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
                if not linked.graph_edited:
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
                if not linked.graph_edited:
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
    """Sync a job's legacy audio/lighting/video/power rows into the unified graph.

    Rows and edges carry a ``legacy_ref``. A run adds what is new, refreshes graph rows that
    were never edited in the graph, removes untouched rows whose legacy source is gone, and
    leaves anything edited in the graph (``graph_edited``) alone. Audio output chains hang off a
    bus node fed by the first patch point (the console).
    """
    builder = Backfill(db, job_id)
    await builder.load_existing()
    with db.no_autoflush:
        await builder.audio_devices()
        await builder.power()
        await builder.channel_lists()
        await builder.channels()
        await builder.audio_outputs()
        await builder.video()
        await builder.lighting()
        await builder.plot_elements()
    with db.no_autoflush:
        await builder.write_edges()
        await builder.plot_links()
        await builder.prune()
    await db.flush()
    result = builder.result
    for row in [*builder.devices.values(), *builder.edge_rows.values()]:
        is_new = row.id not in builder.loaded_revisions
        changed = not is_new and row.revision != builder.loaded_revisions[row.id]
        if is_new or changed:
            target = (
                result.changed_devices if isinstance(row, GraphDevice) else result.changed_edges
            )
            target.append(row.id)
        if changed:
            result.updated += 1
    await db.commit()
    await publish_changes(db, job_id, result)
    return result


async def publish_changes(db: AsyncSession, job_id: uuid.UUID, result: BackfillResult) -> None:
    """Tell open workspaces what a sync changed (nothing is sent when nothing changed)."""
    if not (
        result.changed_devices
        or result.changed_edges
        or result.removed_devices
        or result.removed_edges
    ):
        return
    from app.domains.audio.ws import publish_job_event
    from app.domains.graph import schemas

    for device_id in dict.fromkeys(result.changed_devices):
        device = await db.get(GraphDevice, device_id)
        if device is not None:
            payload = schemas.GraphDeviceRead.model_validate(device).model_dump(mode="json")
            await publish_job_event(job_id, "graph.device.upsert", payload)
    for edge_id in dict.fromkeys(result.changed_edges):
        edge = await db.get(ConnectionEdge, edge_id)
        if edge is not None:
            payload = schemas.ConnectionEdgeRead.model_validate(edge).model_dump(mode="json")
            await publish_job_event(job_id, "graph.edge.upsert", payload)
    for edge_id in result.removed_edges:
        await publish_job_event(job_id, "graph.edge.delete", {"id": str(edge_id)})
    for device_id, edge_ids in result.removed_devices:
        await publish_job_event(
            job_id,
            "graph.device.delete",
            {"id": str(device_id), "edge_ids": [str(e) for e in edge_ids]},
        )
