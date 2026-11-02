import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.ids import power_id_of, public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice

FAN_OUT = 64

FIXTURE_ATTRS = (
    "universe",
    "dmx_address",
    "fixture_type",
    "channel_mode",
    "footprint",
    "location",
    "gel",
    "purpose",
)
MIRRORED_EDGE_TABLES = {
    "channel_patch_points",
    "output_patch_points",
    "channel_list_outputs",
    "stage_plot_elements.link",
    "device.power",
}


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
        self.video_inputs: dict[uuid.UUID, GraphDevice] = {}
        self.rigging_points: dict[uuid.UUID, GraphDevice] = {}
        self.power_nodes: dict[uuid.UUID, GraphDevice] = {}
        self.result = BackfillResult()

    async def load_existing(self) -> None:
        for device in (
            await self.db.scalars(select(GraphDevice).where(GraphDevice.job_id == self.job_id))
        ).all():
            if device.legacy_ref:
                self.devices[device.legacy_ref] = device
                if not device.legacy_ref.startswith("device:"):
                    self.loaded_devices.add(device.legacy_ref)  # a device's ref is its identity
                self.loaded_revisions[device.id] = device.revision
            power_id = power_id_of(device)
            if power_id is not None:
                # power nodes live only in the graph; loads hold the power node's public id
                self.power_nodes[power_id] = device
            if device.kind == "rigging_point":
                # rigging points live only in the graph; loads hold the node's public id
                self.rigging_points[public_id(device)] = device
            if device.kind == "video_input":
                # video inputs live only in the graph; plot elements link them by public id
                self.video_inputs[public_id(device)] = device
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
        # A port made up by the sync stands for "the inputs/outputs of this signal" on a device
        # whose real connectors are unknown, so it takes many cables (a switcher's video inputs
        # all end up on the same generic port). Ports a user defines keep their own capacity.
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

    async def audio_lists(self) -> None:
        """Channel lists, channels and outputs are graph nodes (audio_native.py); the sync draws
        the patch edges from their points."""
        from app.domains.graph import audio_native

        await audio_native.sync_edges(self)

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
        """Remove graph rows whose legacy source is gone: existence follows the legacy editors."""
        gone_edges = [self.edge_rows[ref] for ref in self.loaded_edges - self.seen_edges]
        gone_devices = {
            self.devices[ref].id: self.devices[ref]
            for ref in self.loaded_devices - self.seen_devices
            if ref in self.devices
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
        """Plot elements are graph nodes (plot_native.py); the sync draws their link edges."""
        from app.domains.graph import plot_native

        await plot_native.sync_links(self)

    async def power(self) -> None:
        """Power nodes live on the graph (power_native.py); the sync only draws what plugs in."""
        await self._device_power()

    async def _device_power(self) -> None:
        """Devices plugged into a power node get a power edge from it.

        A device holds its feeder as the graph node id of the power host (``power_node_id``) and
        ``power_connector``. A device that hosts a fixture has the fixture's load there instead; its
        edge is the fixture's (``fixtures_native.sync_power_edges``).
        """
        hosts = {str(h.id): h for h in self.power_nodes.values()}
        for ref, node in list(self.devices.items()):
            if not ref.startswith("device:"):
                continue
            attributes = node.attributes or {}
            feeder = hosts.get(attributes.get("power_node_id"))
            if feeder is None or attributes.get("fixture_id") or feeder.id == node.id:
                continue
            connector = attributes.get("power_connector") or ""
            self.edge(
                f"device.power:{ref.partition(':')[2]}",
                "power",
                feeder,
                self.port(feeder, "out", "power", connector),
                node,
                self.port(node, "in", "power", connector),
                attributes={"connector": connector},
            )


class _JobLock(asyncio.Lock):
    """An asyncio lock that remembers which task holds it, so that task can sync inside it.

    A handler that holds the job lock (a bulk create) and then needs the graph synced (a fixture on
    a device it just made) must not wait for itself: ``backfill_job`` runs the sync directly when
    the caller already owns the lock.
    """

    owner: asyncio.Task | None = None

    async def acquire(self) -> bool:
        await super().acquire()
        self.owner = asyncio.current_task()
        return True

    def release(self) -> None:
        self.owner = None
        super().release()


_JOB_LOCKS: dict[uuid.UUID, _JobLock] = {}


def job_lock(job_id: uuid.UUID) -> asyncio.Lock:
    """The per-job lock syncs queue on; also used to make check-then-insert writes atomic."""
    return _JOB_LOCKS.setdefault(job_id, _JobLock())


async def backfill_job(db: AsyncSession, job_id: uuid.UUID) -> BackfillResult:
    """Sync one job into the graph, one sync at a time per job.

    Two overlapping syncs would both miss the rows the other is about to insert and create
    duplicates, so syncs queue on a per-job lock (in this process) and on a Postgres advisory
    lock (across workers, held until the sync commits).
    """
    lock = job_lock(job_id)
    if getattr(lock, "owner", None) is asyncio.current_task():
        return await _backfill_job_locked(db, job_id)  # this task already holds the lock
    async with lock:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            key = job_id.int & 0x7FFFFFFFFFFFFFFF
            await db.execute(text("select pg_advisory_xact_lock(:key)"), {"key": key})
        return await _backfill_job_locked(db, job_id)


async def _backfill_job_locked(db: AsyncSession, job_id: uuid.UUID) -> BackfillResult:
    """Draw a job's derived edges from its graph nodes (every domain is graph-native).

    Nodes hold the data; this adds, refreshes and prunes the edges that are derived from it: the
    patch edges from the points of channels and outputs (``audio_native.sync_edges``), the plot
    element links (``plot_native.sync_links``) and the power edge of a plugged device. An edge
    carries a ``legacy_ref`` that names what it was derived from (the point id, the element and
    role), so a run keeps ids stable, updates what changed and removes what no longer follows
    from a node. An edge whose ``phase`` was set in the graph (``graph_edited``) keeps it.
    """
    builder = Backfill(db, job_id)
    await builder.load_existing()
    with db.no_autoflush:
        await builder.power()
        await builder.audio_lists()
        await builder.plot_elements()
    with db.no_autoflush:
        await builder.write_edges()
        await builder.prune()
    await db.flush()
    # a sync resets a device node's ports from its connector groups: put the power ports back
    from app.domains.graph import power_native

    await power_native.rebuild_feeds(db, job_id)
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
