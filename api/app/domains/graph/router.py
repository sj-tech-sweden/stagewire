import json
import xml.etree.ElementTree as ET
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.versioning import run_versioned_delete, run_versioned_write
from app.domains.audio import wwb_store
from app.domains.audio.exports import get_exporter, list_exporters
from app.domains.audio.models import ProductionJob
from app.domains.audio.ws import publish_job_event
from app.domains.audio.wwb import match_wireless_rows, parse_wwb_show_file
from app.domains.auth.deps import get_current_user
from app.domains.connectors.service import refresh_power_connectors
from app.domains.graph import (
    audio_native,
    backfill,
    devices_native,
    dmx_native,
    fixtures_native,
    mirror,
    plot_native,
    power_native,
    readers,
    rigging_native,
    schemas,
    topology,
    video_native,
)
from app.domains.graph.ids import power_id_of
from app.domains.graph.models import ConnectionEdge, GraphDevice, belongs_to, scope_filter
from app.domains.stockwire.client import StockwireClient
from app.domains.stockwire.config import load_integration_config

router = APIRouter(
    prefix="/jobs/{job_id}/graph",
    tags=["graph"],
    dependencies=[Depends(get_current_user), Depends(refresh_power_connectors)],
)

MAX_BATCH = 200
STOCKWIRE_ASSET_ATTRIBUTES = frozenset(
    {
        "stockwire_asset_id",
        "stockwire_asset_code",
        "stockwire_asset_tag",
        "stockwire_asset_serial",
        "stockwire_asset_barcode",
        "stockwire_asset_qr_code",
        "stockwire_asset_rfid",
        "stockwire_asset_description",
    }
)


async def get_stockwire_client(db: AsyncSession = Depends(get_db)) -> StockwireClient:
    cfg = await load_integration_config(db)
    return StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])


def _as_dict(row: GraphDevice | ConnectionEdge) -> dict:
    data = {column.key: getattr(row, column.key) for column in row.__mapper__.column_attrs}
    # Channels are fixed-shape nodes: guarantee the `in`/`out` ports exist even on nodes stored
    # before the `in` port was introduced, so edge validation and traces never reject a channel as
    # a valid endpoint. Purely a read-time view — the ORM row is left untouched.
    if getattr(row, "kind", None) == "channel" and isinstance(data.get("ports"), list):
        data["ports"] = audio_native.normalize_channel_ports(data["ports"])
    return data


async def _require_job(db: AsyncSession, job_id: UUID) -> None:
    if await db.get(ProductionJob, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")


async def _device(db: AsyncSession, job_id: UUID, device_id: UUID) -> GraphDevice:
    device = await db.get(GraphDevice, device_id)
    if device is None or device.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


def _require_physical_asset_target(device: GraphDevice) -> None:
    if not devices_native.is_physical_gear(device):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Stockwire assets can only be linked to physical gear",
        )


async def _edge(db: AsyncSession, job_id: UUID, edge_id: UUID) -> ConnectionEdge:
    edge = await db.get(ConnectionEdge, edge_id)
    if edge is None or edge.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edge not found")
    return edge


async def _all_edges(db: AsyncSession, job_id: UUID) -> list[ConnectionEdge]:
    return list(
        (await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))).all()
    )


async def _all_devices(db: AsyncSession, job_id: UUID) -> list[GraphDevice]:
    return list(
        (
            await db.scalars(
                select(GraphDevice)
                .where(GraphDevice.job_id == job_id)
                .order_by(GraphDevice.position, GraphDevice.created_at)
            )
        ).all()
    )


async def read_job_graph(db: AsyncSession, job_id: UUID) -> schemas.GraphRead:
    """Read-only projection of a job's device/edge graph.

    Public entry point used by other domains (e.g. the share view) so they don't have to reach
    into this router's private ``_all_devices``/``_all_edges`` helpers.
    """
    return schemas.GraphRead(
        devices=[_device_payload(d) for d in await _all_devices(db, job_id)],
        edges=[schemas.ConnectionEdgeRead.model_validate(e) for e in await _all_edges(db, job_id)],
    )


def _device_payload(device: GraphDevice) -> dict:
    payload = schemas.GraphDeviceRead.model_validate(device).model_dump(mode="json")
    # ``sound_list_id`` / ``video_list_id`` live in the node's ``attributes`` dict, so the ORM
    # object has no top-level column to read them from; copy them across for the frontend.
    payload["sound_list_id"] = device.attributes.get("sound_list_id")
    payload["video_list_id"] = device.attributes.get("video_list_id")
    # Channels are fixed-shape nodes: guarantee the `in`/`out` ports exist even on nodes stored
    # before the `in` port was introduced, so the frontend shows channels as valid endpoints.
    if device.kind == "channel" and isinstance(payload.get("ports"), list):
        payload["ports"] = audio_native.normalize_channel_ports(payload["ports"])
    return payload


@router.get("", response_model=schemas.GraphRead)
async def get_graph(job_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.GraphRead:
    await _require_job(db, job_id)
    return schemas.GraphRead(
        devices=[_device_payload(d) for d in await _all_devices(db, job_id)],
        edges=[schemas.ConnectionEdgeRead.model_validate(e) for e in await _all_edges(db, job_id)],
    )


@router.post("/devices", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_device(
    job_id: UUID, payload: schemas.GraphDeviceCreate, db: AsyncSession = Depends(get_db)
) -> GraphDevice:
    await _require_job(db, job_id)
    fields = payload.model_dump()
    if fields["kind"] == "plot_element":
        fields = plot_native.normalize_new(fields)
    device = GraphDevice(job_id=job_id, **fields)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return device


@router.post("/devices/batch", response_model=list[schemas.GraphDeviceRead], status_code=201)
async def create_devices_batch(
    job_id: UUID, payload: list[schemas.GraphDeviceCreate], db: AsyncSession = Depends(get_db)
) -> list[GraphDevice]:
    await _require_job(db, job_id)
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} devices")
    devices = []
    for item in payload:
        fields = item.model_dump()
        if fields["kind"] == "plot_element":
            fields = plot_native.normalize_new(fields)
        devices.append(GraphDevice(job_id=job_id, **fields))
    db.add_all(devices)
    await db.commit()
    for device in devices:
        await db.refresh(device)
        await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return devices


@router.patch("/devices/{device_id}", response_model=schemas.GraphDeviceRead)
async def update_device(
    job_id: UUID,
    device_id: UUID,
    payload: schemas.GraphDeviceUpdate,
    db: AsyncSession = Depends(get_db),
) -> GraphDevice:
    device = await _device(db, job_id, device_id)
    data = dmx_native.translate_patch(
        device,
        video_native.translate_patch(
            device, payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
        ),
    )
    if "stockwire_device_id" in data or STOCKWIRE_ASSET_ATTRIBUTES.intersection(
        (data.get("attributes") or {}).keys()
    ):
        _require_physical_asset_target(device)

    async def apply() -> GraphDevice:
        for key, value in mirror.merged_attributes(device, data).items():
            setattr(device, key, value)
        await db.flush()  # the version check fails here, before the legacy row is touched
        await dmx_native.after_patch(db, device, data)
        await power_native.after_patch(db, job_id, device, data)
        await fixtures_native.after_patch(db, job_id, device, data)
        await plot_native.after_patch(db, job_id, device, data)
        await audio_native.after_patch(db, device, data)
        await devices_native.after_patch(device, data)
        mirrored = await mirror.device_to_legacy(db, job_id, device, data) or (
            # a channel's number and an output's order are on its edges: redraw them
            device.kind in audio_native.KINDS and not device.legacy_ref
        )
        await db.commit()
        if mirrored:
            await backfill.backfill_job(db, job_id)
        await db.refresh(device)
        return device

    device = await run_versioned_write(
        db,
        device,
        payload.expected_revision,
        schemas.GraphDeviceRead,
        apply,
        lambda: db.get(GraphDevice, device_id),
    )
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return _device_payload(device)


@router.post("/devices/{device_id}/bind-asset", response_model=schemas.GraphDeviceRead)
async def bind_stockwire_asset(
    job_id: UUID,
    device_id: UUID,
    payload: schemas.AssetBind,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await bind_asset_for_job(db, job_id, device_id, payload, payload.expected_revision)


@router.delete("/devices/{device_id}/asset-binding", response_model=schemas.GraphDeviceRead)
async def unbind_stockwire_asset(
    job_id: UUID,
    device_id: UUID,
    expected_revision: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await unbind_asset_for_job(db, job_id, device_id, expected_revision)


async def bind_asset_for_job(
    db: AsyncSession,
    job_id: UUID,
    device_id: UUID,
    payload: schemas.AssetBind,
    expected_revision: int,
) -> dict:
    """Bind a physical Stockwire asset and publish the updated device to job subscribers."""
    device = await _device(db, job_id, device_id)
    _require_physical_asset_target(device)
    resolved = None
    cfg = await load_integration_config(db)
    if cfg.get("enabled"):
        client = StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])
        resolved = await client.resolve_asset(payload.asset_id or payload.code)
    if (
        payload.asset_id
        and device.stockwire_product_id
        and resolved
        and resolved.get("product_id") is not None
        and str(resolved["product_id"]) != str(device.stockwire_product_id)
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Selected Stockwire asset does not belong to the linked product",
        )

    attrs = dict(device.attributes or {})
    # Older bindings stored the canonical ID (or an unresolved scan code) in attributes.
    # Remove that duplicate when rewriting so the top-level field is the only current ID.
    attrs.pop("stockwire_asset_id", None)
    attrs["stockwire_asset_code"] = payload.code
    attrs["stockwire_asset_tag"] = (resolved or {}).get("asset_tag") or payload.tag
    attrs["stockwire_asset_serial"] = (resolved or {}).get("serial_number") or payload.serial
    attrs["stockwire_asset_barcode"] = (resolved or {}).get("barcode") or payload.barcode
    attrs["stockwire_asset_qr_code"] = (resolved or {}).get("qr_code") or payload.qr_code
    attrs["stockwire_asset_rfid"] = (resolved or {}).get("rfid") or payload.rfid
    attrs["stockwire_asset_description"] = (resolved or {}).get(
        "description"
    ) or payload.description

    async def apply() -> GraphDevice:
        device.attributes = attrs
        # This is the single canonical inventory ID used by catalog/case integrations. Keep raw
        # scans in stockwire_asset_code instead of putting an unverified code in this field.
        device.stockwire_device_id = (
            str(resolved["asset_id"]) if resolved and resolved.get("asset_id") else payload.asset_id
        )
        await db.commit()
        await db.refresh(device)
        return device

    device = await run_versioned_write(
        db,
        device,
        expected_revision,
        schemas.GraphDeviceRead,
        apply,
        lambda: db.get(GraphDevice, device_id),
    )
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return _device_payload(device)


async def unbind_asset_for_job(
    db: AsyncSession, job_id: UUID, device_id: UUID, expected_revision: int
) -> dict:
    """Clear a device's local Stockwire asset link and publish the updated device."""
    device = await _device(db, job_id, device_id)
    _require_physical_asset_target(device)
    attrs = dict(device.attributes or {})
    for key in (
        "stockwire_asset_id",
        "stockwire_asset_code",
        "stockwire_asset_tag",
        "stockwire_asset_serial",
        "stockwire_asset_barcode",
        "stockwire_asset_qr_code",
        "stockwire_asset_rfid",
        "stockwire_asset_description",
    ):
        attrs[key] = None

    async def apply() -> GraphDevice:
        device.attributes = attrs
        device.stockwire_device_id = None
        await db.commit()
        await db.refresh(device)
        return device

    device = await run_versioned_write(
        db,
        device,
        expected_revision,
        schemas.GraphDeviceRead,
        apply,
        lambda: db.get(GraphDevice, device_id),
    )
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    return _device_payload(device)


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    job_id: UUID,
    device_id: UUID,
    expected_revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await _device(db, job_id, device_id)
    touching = [
        e for e in await _all_edges(db, job_id) if device_id in (e.src_device_id, e.dst_device_id)
    ]
    removed_edges = [str(e.id) for e in touching]
    removed_nodes: list[str] = []

    async def remove() -> None:
        for edge in touching:
            await db.delete(edge)
        if power_id_of(device) is not None:
            # the engine's rules (nothing fed from it, nothing plugged in); a device keeps living
            await power_native.check_deletable(db, job_id, power_id_of(device))
        if audio_native.is_native(device) and device.kind == audio_native.LIST:
            # a list takes its channels and outputs with it
            child_nodes, child_edges = await audio_native.delete_children(db, device)
            removed_nodes.extend(child_nodes)
            removed_edges.extend(child_edges)
        if device.kind == "rigging_point":
            await rigging_native.clear_references(db, device)
        if device.kind in video_native.VIDEO_KINDS:
            child_nodes, child_edges = await video_native.clear_references(db, device)
            removed_nodes.extend(child_nodes)
            removed_edges.extend(child_edges)
        await db.delete(device)
        await db.flush()
        await dmx_native.drop_node(db, job_id, device_id)
        if power_id_of(device) is not None:
            await power_native.rebuild_feeds(db, job_id)
        try:
            await mirror.delete_device_twin(db, job_id, device)
        except HTTPException:
            await db.rollback()
            raise
        await db.commit()

    await run_versioned_delete(
        db,
        device,
        expected_revision,
        schemas.GraphDeviceRead,
        remove,
        lambda: db.get(GraphDevice, device_id),
    )
    for child_id in removed_nodes:
        await publish_job_event(job_id, "graph.device.delete", {"id": child_id, "edge_ids": []})
    await publish_job_event(
        job_id, "graph.device.delete", {"id": str(device_id), "edge_ids": removed_edges}
    )


@router.post("/edges", response_model=schemas.ConnectionEdgeRead, status_code=201)
async def create_edge(
    job_id: UUID,
    payload: schemas.ConnectionEdgeCreate,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> ConnectionEdge:
    src = await _device(db, job_id, payload.src_device_id)
    dst = await _device(db, job_id, payload.dst_device_id)
    existing = await _all_edges(db, job_id)
    link_attrs: dict | None = None
    if payload.signal == "link":
        link_attrs = await mirror.link_edge_to_legacy(db, src, dst, payload.dst_port)
        for old in existing:
            if (old.attributes or {}).get("legacy_ref") == link_attrs["legacy_ref"]:
                await db.delete(old)
        existing = [
            e
            for e in existing
            if (e.attributes or {}).get("legacy_ref") != link_attrs["legacy_ref"]
        ]
    if topology.would_create_cycle(
        [_as_dict(e) for e in existing if e.signal == payload.signal],
        str(src.id),
        str(dst.id),
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Connection would form a loop")
    issues = topology.validate_edge(
        payload.model_dump(mode="json"),
        _as_dict(src),
        _as_dict(dst),
        [_as_dict(e) for e in existing],
    )
    if issues and (not force or topology.blocks_forced(issues)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_connection",
                "issues": [schemas.IssueRead(**vars(i)).model_dump() for i in issues],
            },
        )
    edge = ConnectionEdge(job_id=job_id, **payload.model_dump())
    if link_attrs:
        edge.attributes = {**(edge.attributes or {}), **link_attrs}
    db.add(edge)
    await db.commit()
    await db.refresh(edge)
    await publish_job_event(
        job_id,
        "graph.edge.upsert",
        schemas.ConnectionEdgeRead.model_validate(edge).model_dump(mode="json"),
    )
    return edge


@router.patch("/edges/{edge_id}", response_model=schemas.ConnectionEdgeRead)
async def update_edge(
    job_id: UUID,
    edge_id: UUID,
    payload: schemas.ConnectionEdgeUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConnectionEdge:
    edge = await _edge(db, job_id, edge_id)
    data = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)

    async def apply() -> ConnectionEdge:
        protect = mirror.edge_needs_protection(edge, data)
        for key, value in mirror.merged_attributes(edge, data).items():
            setattr(edge, key, value)
        if protect:
            edge.graph_edited = True
        await db.flush()
        mirrored = await mirror.edge_to_legacy(db, job_id, edge, data)
        await db.commit()
        if mirrored:
            await backfill.backfill_job(db, job_id)
        await db.refresh(edge)
        return edge

    edge = await run_versioned_write(
        db,
        edge,
        payload.expected_revision,
        schemas.ConnectionEdgeRead,
        apply,
        lambda: db.get(ConnectionEdge, edge_id),
    )
    await publish_job_event(
        job_id,
        "graph.edge.upsert",
        schemas.ConnectionEdgeRead.model_validate(edge).model_dump(mode="json"),
    )
    return edge


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    job_id: UUID,
    edge_id: UUID,
    expected_revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> None:
    edge = await _edge(db, job_id, edge_id)

    async def remove() -> None:
        await db.delete(edge)
        await db.flush()
        mirrored = await mirror.delete_edge_twin(db, job_id, edge)
        await db.commit()
        if mirrored:
            await backfill.backfill_job(db, job_id)

    await run_versioned_delete(
        db,
        edge,
        expected_revision,
        schemas.ConnectionEdgeRead,
        remove,
        lambda: db.get(ConnectionEdge, edge_id),
    )
    await publish_job_event(job_id, "graph.edge.delete", {"id": str(edge_id)})


@router.get("/devices/{device_id}/trace", response_model=schemas.TraceRead)
async def trace_device(
    job_id: UUID,
    device_id: UUID,
    direction: str = Query(pattern="^(upstream|downstream)$"),
    signal: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> schemas.TraceRead:
    await _device(db, job_id, device_id)
    edges = await _all_edges(db, job_id)
    devices = {str(d.id): _as_dict(d) for d in await _all_devices(db, job_id)}
    result = topology.trace([_as_dict(e) for e in edges], str(device_id), direction, signal=signal)
    by_id = {str(e.id): e for e in edges}
    issues = [
        i
        for hop in result.hops
        for i in topology.validate_edge(
            _as_dict(by_id[str(hop.edge["id"])]),
            devices.get(str(hop.edge["src_device_id"])),
            devices.get(str(hop.edge["dst_device_id"])),
            [_as_dict(e) for e in edges],
        )
    ]
    return schemas.TraceRead(
        root=result.root,
        direction=direction,
        truncated=result.truncated,
        hops=[
            schemas.HopRead(
                depth=h.depth,
                device_id=h.device_id,
                edge=schemas.ConnectionEdgeRead.model_validate(by_id[str(h.edge["id"])]),
            )
            for h in result.hops
        ],
        issues=[schemas.IssueRead(**vars(i)) for i in issues],
    )


@router.get("/validate", response_model=list[schemas.IssueRead])
async def validate_graph(
    job_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.IssueRead]:
    await _require_job(db, job_id)
    edges = await _all_edges(db, job_id)
    devices = {str(d.id): _as_dict(d) for d in await _all_devices(db, job_id)}
    rows = [_as_dict(e) for e in edges]
    return [
        schemas.IssueRead(**vars(issue))
        for row in rows
        for issue in topology.validate_edge(
            row,
            devices.get(str(row["src_device_id"])),
            devices.get(str(row["dst_device_id"])),
            rows,
        )
    ]


@router.get("/power-load", response_model=schemas.PhaseLoadRead)
async def power_load(job_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.PhaseLoadRead:
    await _require_job(db, job_id)
    devices = {str(d.id): _as_dict(d) for d in await _all_devices(db, job_id)}
    loads = topology.phase_loads(devices, [_as_dict(e) for e in await _all_edges(db, job_id)])
    from app.domains.rigging import router as rigging_router

    # With a power tree the load is what the tree evaluates (everything plugged in, spread over the
    # phases as the outputs say), summed over the sources; the per-edge figure above only knows
    # edges that carry a phase and so reads 0 for gear plugged into a node.
    tree = await rigging_router.rigging_summary(job_id=job_id, venue_id=None, db=db)
    sources = [n for n in tree["nodes"] if n["kind"] == "source"]
    if sources:
        loads = {p: round(sum(n["watts"].get(p, 0.0) for n in sources), 1) for p in topology.PHASES}
    # Imbalance is measured across all three phases on purpose: a job that loads one phase and
    # leaves the others empty should be told so, to look for outlets on another phase.
    peak, low = max(loads.values()), min(loads.values())
    return schemas.PhaseLoadRead(
        **loads,
        imbalance_pct=round((peak - low) / peak * 100, 1) if peak else 0.0,
        limit_w=topology.phase_limit_w(devices),
    )


@router.post("/devices/{device_id}/request-stockwire", response_model=schemas.GraphDeviceRead)
async def request_stockwire_booking(
    job_id: UUID,
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    sw: StockwireClient = Depends(get_stockwire_client),
) -> GraphDevice:
    job = await db.get(ProductionJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    device = await _device(db, job_id, device_id)
    if not job.stockwire_job_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is not linked to a Stockwire job")
    if not device.stockwire_product_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Device is not bound to a Stockwire product"
        )
    if device.stockwire_booked:
        return device
    device.stockwire_request_status = "pending"
    await db.commit()
    await db.refresh(device)
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    try:
        await sw.add_requirement(
            job.stockwire_job_id,
            {
                "product_id": device.stockwire_product_id,
                "quantity_required": 1,
                "label": device.stockwire_product_name or device.name,
                "notes": f"Requested from Stagewire: {device.name}",
            },
        )
        device.stockwire_request_status = "requested"
        device.stockwire_booked = True
    except Exception:  # noqa: BLE001
        device.stockwire_request_status = "failed"
    await db.commit()
    await db.refresh(device)
    await publish_job_event(job_id, "graph.device.upsert", _device_payload(device))
    if device.stockwire_request_status == "failed":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stockwire rejected the request")
    return device


@router.post("/backfill", response_model=schemas.BackfillRead)
async def backfill_graph(job_id: UUID, db: AsyncSession = Depends(get_db)) -> schemas.BackfillRead:
    await _require_job(db, job_id)
    result = await backfill.backfill_job(db, job_id)
    return schemas.BackfillRead(
        devices=result.devices,
        edges=result.edges,
        skipped=result.skipped,
        updated=result.updated,
        removed=result.removed,
        notes=result.notes,
    )


@router.get("/export-plugins")
async def export_plugins(job_id: UUID, db: AsyncSession = Depends(get_db)) -> list[dict]:
    await _require_job(db, job_id)
    return [
        {
            "key": e.key,
            "label": e.label,
            "description": e.description,
            "extension": e.file_extension,
        }
        for e in list_exporters()
    ]


@router.get("/lists/{list_id}/export")
async def export_list(
    job_id: UUID, list_id: UUID, plugin: str, db: AsyncSession = Depends(get_db)
) -> Response:
    """Console export of a channel list read from the graph (same plugins as the legacy export)."""
    await _require_job(db, job_id)
    exporter = get_exporter(plugin)
    if exporter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown export plugin")
    view = await readers.load_channel_list(db, job_id, list_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    # If this list has imported a .shw before, let the exporter round-trip it.
    stored = await wwb_store.get_show_file(db, list_id)
    if stored is not None:
        view[0].wwb_show_file_content = stored
    result = exporter.export(*view)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


_WWB_WIRELESS_FIELDS = ("wireless_frequency_mhz", "wireless_group", "wireless_channel")


@router.post("/lists/{list_id}/wireless-workbench/parse")
async def parse_wireless_workbench(
    job_id: UUID,
    list_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Preview a Shure Wireless Workbench ``.shw`` before importing.

    Parses the file and returns the coordinated channels (``rows``), the list's existing
    wireless channels (``channels``) and a suggested mapping (``suggested_channel_id`` per
    row). The client edits the mapping and posts it back to the import endpoint.
    """
    await _require_job(db, job_id)
    raw = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_wwb_show_file(raw)
    except ET.ParseError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid Wireless Workbench file: {exc}"
        ) from exc
    view = await readers.load_channel_list(db, job_id, list_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    _, channels, _ = view
    wireless = [c for c in channels if getattr(c, "input_type", None) == "wireless"]
    matched, _unmatched, method = match_wireless_rows(wireless, rows)
    row_to_channel = {id(row): c.id for c, row in matched}

    preview_rows = [
        {
            "index": index,
            "name": row.get("name"),
            "wireless_frequency_mhz": row.get("wireless_frequency_mhz"),
            "wireless_group": row.get("wireless_group"),
            "wireless_channel": row.get("wireless_channel"),
            "suggested_channel_id": row_to_channel.get(id(row)),
        }
        for index, row in enumerate(rows)
    ]
    preview_channels = [
        {
            "id": c.id,
            "channel_number": c.channel_number,
            "source_label": getattr(c, "source_label", None),
            "wireless_pack": getattr(c, "wireless_pack", None),
            "wireless_frequency_mhz": getattr(c, "wireless_frequency_mhz", None),
            "wireless_group": getattr(c, "wireless_group", None),
            "wireless_channel": getattr(c, "wireless_channel", None),
        }
        for c in wireless
    ]
    return {
        "rows": preview_rows,
        "channels": preview_channels,
        "matched_by": method,
        "filename": file.filename,
    }


@router.post("/lists/{list_id}/wireless-workbench/import")
async def import_wireless_workbench(
    job_id: UUID,
    list_id: UUID,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Import a Shure Wireless Workbench ``.shw`` show file onto the list's wireless channels.

    If ``mapping`` (a JSON list of ``{"row": <index>, "channel_id": <uuid>}``) is given,
    only those rows are applied; otherwise channels are matched automatically by name
    (channel name, pack or source label), falling back to order. The imported file is
    stored so it can later be re-exported with Stagewire's frequencies written back.
    """
    await _require_job(db, job_id)
    raw = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_wwb_show_file(raw)
    except ET.ParseError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid Wireless Workbench file: {exc}"
        ) from exc
    view = await readers.load_channel_list(db, job_id, list_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    _, channels, _ = view
    wireless_by_id = {c.id: c for c in channels if getattr(c, "input_type", None) == "wireless"}

    if mapping:
        try:
            mapping_list = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Invalid mapping JSON: {exc}"
            ) from exc
        pairs: list[tuple] = []
        for entry in mapping_list:
            row_index = entry.get("row")
            channel_id = entry.get("channel_id")
            if channel_id is None or row_index is None:
                continue
            try:
                channel_id = UUID(str(channel_id))
            except (ValueError, TypeError):
                continue
            if channel_id in wireless_by_id and 0 <= int(row_index) < len(rows):
                pairs.append((wireless_by_id[channel_id], rows[int(row_index)]))
    else:
        pairs, _unmatched, _method = match_wireless_rows(list(wireless_by_id.values()), rows)

    updated_ids: list[UUID] = []
    for channel, row in pairs:
        data = {key: row[key] for key in _WWB_WIRELESS_FIELDS if key in row}
        await audio_native.update_channel(db, channel.id, data, job_id)
        updated_ids.append(channel.id)
    await wwb_store.upsert_show_file(db, list_id, raw, file.filename or "show.shw", job_id=job_id)
    await db.commit()
    await audio_native.publish_nodes(db, job_id, updated_ids)
    if updated_ids:
        await publish_job_event(job_id, "list.upsert", {"id": str(list_id)})
    matched_rows = {id(row) for _channel, row in pairs}
    return {
        "matched": len(pairs),
        "updated": len(updated_ids),
        "rows": len(rows),
        "unmatched": [
            row.get("name") or row.get("wireless_pack") or f"row {index + 1}"
            for index, row in enumerate(rows)
            if id(row) not in matched_rows
        ],
    }


# --- venue variant --------------------------------------------------------------------------------
# A venue's Standard Base Rig reuses the job graph editing UX (WorkspaceCanvas + RiggingEditor +
# PowerPanel + patch drawer) so it gets the identical rigging/power treatment. The whole-graph GET
# that the store reads lives on the venues router (`GET /venues/{venue_id}/graph`, which 404s for an
# unknown venue); these routes provide the incremental device/edge edits (the same ones a job makes)
# and skip the job-only machinery (mirror/backfill/publish) because a venue has no legacy rows, no
# per-job websocket and no job lock. Every write is scoped by `venue_id` (job_id is always None), so
# a venue and a job never share rows, and the job path above is untouched.
venue_router = APIRouter(
    prefix="/venues/{venue_id}/graph",
    tags=["graph:venue"],
    dependencies=[Depends(get_current_user)],
)


async def _venue_device(db: AsyncSession, venue_id: UUID, device_id: UUID) -> GraphDevice:
    device = await db.get(GraphDevice, device_id)
    if device is None or not belongs_to(device, None, venue_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


async def _venue_edge(db: AsyncSession, venue_id: UUID, edge_id: UUID) -> ConnectionEdge:
    edge = await db.get(ConnectionEdge, edge_id)
    if edge is None or not belongs_to(edge, None, venue_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Edge not found")
    return edge


async def _venue_all_edges(db: AsyncSession, venue_id: UUID) -> list[ConnectionEdge]:
    return list(
        (
            await db.scalars(
                select(ConnectionEdge).where(scope_filter(ConnectionEdge, None, venue_id))
            )
        ).all()
    )


@venue_router.post("/devices", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_device_venue(
    venue_id: UUID, payload: schemas.GraphDeviceCreate, db: AsyncSession = Depends(get_db)
) -> GraphDevice:
    fields = payload.model_dump()
    if fields["kind"] == "plot_element":
        fields = plot_native.normalize_new(fields)
    device = GraphDevice(job_id=None, venue_id=venue_id, **fields)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@venue_router.post("/devices/batch", response_model=list[schemas.GraphDeviceRead], status_code=201)
async def create_devices_batch_venue(
    venue_id: UUID, payload: list[schemas.GraphDeviceCreate], db: AsyncSession = Depends(get_db)
) -> list[GraphDevice]:
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} devices")
    devices = []
    for item in payload:
        fields = item.model_dump()
        if fields["kind"] == "plot_element":
            fields = plot_native.normalize_new(fields)
        devices.append(GraphDevice(job_id=None, venue_id=venue_id, **fields))
    db.add_all(devices)
    await db.commit()
    for device in devices:
        await db.refresh(device)
    return devices


@venue_router.patch("/devices/{device_id}", response_model=schemas.GraphDeviceRead)
async def update_device_venue(
    venue_id: UUID,
    device_id: UUID,
    payload: schemas.GraphDeviceUpdate,
    db: AsyncSession = Depends(get_db),
) -> GraphDevice:
    device = await _venue_device(db, venue_id, device_id)
    data = dmx_native.translate_patch(
        device,
        video_native.translate_patch(
            device, payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
        ),
    )

    async def apply() -> GraphDevice:
        for key, value in mirror.merged_attributes(device, data).items():
            setattr(device, key, value)
        await db.flush()
        await dmx_native.after_patch(db, device, data, venue_id=venue_id)
        await power_native.after_patch(db, None, device, data, venue_id=venue_id)
        await fixtures_native.after_patch(db, None, device, data, venue_id=venue_id)
        await plot_native.after_patch(db, None, device, data, venue_id=venue_id)
        await audio_native.after_patch(db, device, data)
        await devices_native.after_patch(device, data)
        await db.commit()
        await db.refresh(device)
        return device

    return await run_versioned_write(
        db,
        device,
        payload.expected_revision,
        schemas.GraphDeviceRead,
        apply,
        lambda: db.get(GraphDevice, device_id),
    )


@venue_router.delete("/devices/{device_id}", status_code=204)
async def delete_device_venue(
    venue_id: UUID,
    device_id: UUID,
    expected_revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await _venue_device(db, venue_id, device_id)
    touching = [
        e
        for e in await _venue_all_edges(db, venue_id)
        if device_id in (e.src_device_id, e.dst_device_id)
    ]

    async def remove() -> None:
        for edge in touching:
            await db.delete(edge)
        # The venue's power rules still apply, so a node cannot be removed while something hangs
        # from it or is plugged into it (a device keeps living when its power side is cleared).
        if power_id_of(device) is not None:
            await power_native.check_deletable(db, None, power_id_of(device), venue_id=venue_id)
        # A rigging point's references (a device/element hanging on it) are cleared with it.
        if device.kind == "rigging_point":
            await rigging_native.clear_references(db, device, venue_id=venue_id)
        # Video/audio list children are job-coupled (legacy); the venue scope deletes the node and
        # its incident edges (below) — child lists are an extreme edge case on a base rig.
        await db.delete(device)
        await db.flush()
        await dmx_native.drop_node(db, None, device_id, venue_id=venue_id)
        if power_id_of(device) is not None:
            await power_native.rebuild_feeds(db, None, venue_id)
        await db.commit()

    await run_versioned_delete(
        db,
        device,
        expected_revision,
        schemas.GraphDeviceRead,
        remove,
        lambda: db.get(GraphDevice, device_id),
    )


@venue_router.post("/edges", response_model=schemas.ConnectionEdgeRead, status_code=201)
async def create_edge_venue(
    venue_id: UUID,
    payload: schemas.ConnectionEdgeCreate,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> ConnectionEdge:
    src = await _venue_device(db, venue_id, payload.src_device_id)
    dst = await _venue_device(db, venue_id, payload.dst_device_id)
    existing = await _venue_all_edges(db, venue_id)
    if topology.would_create_cycle(
        [_as_dict(e) for e in existing if e.signal == payload.signal],
        str(src.id),
        str(dst.id),
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Connection would form a loop")
    issues = topology.validate_edge(
        payload.model_dump(mode="json"),
        _as_dict(src),
        _as_dict(dst),
        [_as_dict(e) for e in existing],
    )
    if issues and (not force or topology.blocks_forced(issues)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_connection",
                "issues": [schemas.IssueRead(**vars(i)).model_dump() for i in issues],
            },
        )
    edge = ConnectionEdge(job_id=None, venue_id=venue_id, **payload.model_dump())
    db.add(edge)
    await db.commit()
    await db.refresh(edge)
    return edge


@venue_router.patch("/edges/{edge_id}", response_model=schemas.ConnectionEdgeRead)
async def update_edge_venue(
    venue_id: UUID,
    edge_id: UUID,
    payload: schemas.ConnectionEdgeUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConnectionEdge:
    edge = await _venue_edge(db, venue_id, edge_id)
    data = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)

    async def apply() -> ConnectionEdge:
        for key, value in mirror.merged_attributes(edge, data).items():
            setattr(edge, key, value)
        await db.flush()
        # Venue edges skip the legacy mirror: only the graph-native power/fixture patches run.
        await power_native.edge_patch(db, None, edge, data, venue_id=venue_id)
        await fixtures_native.edge_patch(db, None, edge, data, venue_id=venue_id)
        await db.commit()
        await db.refresh(edge)
        return edge

    return await run_versioned_write(
        db,
        edge,
        payload.expected_revision,
        schemas.ConnectionEdgeRead,
        apply,
        lambda: db.get(ConnectionEdge, edge_id),
    )


@venue_router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge_venue(
    venue_id: UUID,
    edge_id: UUID,
    expected_revision: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> None:
    edge = await _venue_edge(db, venue_id, edge_id)

    async def remove() -> None:
        await db.delete(edge)
        await db.flush()
        # A node's own feed cannot be cut here; an extra feed is removed. Fixture power edges
        # unplug.
        await power_native.edge_delete(db, None, edge, venue_id=venue_id)
        await fixtures_native.edge_delete(db, None, edge, venue_id=venue_id)
        await db.commit()

    await run_versioned_delete(
        db,
        edge,
        expected_revision,
        schemas.ConnectionEdgeRead,
        remove,
        lambda: db.get(ConnectionEdge, edge_id),
    )


async def _require_venue(db: AsyncSession, venue_id: UUID) -> None:
    """404 if the venue the editor targets does not exist (a venue graph edit is meaningless then).

    Model import path: ``app.domains.venues.models.Venue``.
    """
    from app.domains.venues.models import Venue

    if await db.get(Venue, venue_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")


async def _venue_all_devices(db: AsyncSession, venue_id: UUID) -> list[GraphDevice]:
    return list(
        (
            await db.scalars(
                select(GraphDevice)
                .where(scope_filter(GraphDevice, None, venue_id))
                .order_by(GraphDevice.position, GraphDevice.created_at)
            )
        ).all()
    )


@venue_router.get("/validate", response_model=list[schemas.IssueRead])
async def validate_graph_venue(
    venue_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[schemas.IssueRead]:
    """Validate every edge in a venue's base-rig graph (same checks as the job graph)."""
    await _require_venue(db, venue_id)
    edges = await _venue_all_edges(db, venue_id)
    devices = {str(d.id): _as_dict(d) for d in await _venue_all_devices(db, venue_id)}
    rows = [_as_dict(e) for e in edges]
    return [
        schemas.IssueRead(**vars(issue))
        for row in rows
        for issue in topology.validate_edge(
            row,
            devices.get(str(row["src_device_id"])),
            devices.get(str(row["dst_device_id"])),
            rows,
        )
    ]


@venue_router.get("/power-load", response_model=schemas.PhaseLoadRead)
async def power_load_venue(
    venue_id: UUID, db: AsyncSession = Depends(get_db)
) -> schemas.PhaseLoadRead:
    """Phase loads for a venue's base rig (same as the job route, scoped by venue)."""
    await _require_venue(db, venue_id)
    devices = {str(d.id): _as_dict(d) for d in await _venue_all_devices(db, venue_id)}
    edges = [_as_dict(e) for e in await _venue_all_edges(db, venue_id)]
    loads = topology.phase_loads(devices, edges)
    # With a power tree the load is what the tree evaluates (everything plugged in, spread over the
    # phases as the outputs say), summed over the sources; the per-edge figure above only knows
    # edges that carry a phase and so reads 0 for gear plugged into a node.
    from app.domains.rigging import router as rigging_router

    tree = await rigging_router.rigging_summary(job_id=None, venue_id=venue_id, db=db)
    sources = [n for n in tree["nodes"] if n["kind"] == "source"]
    if sources:
        loads = {p: round(sum(n["watts"].get(p, 0.0) for n in sources), 1) for p in topology.PHASES}
    peak, low = max(loads.values()), min(loads.values())
    return schemas.PhaseLoadRead(
        **loads,
        imbalance_pct=round((peak - low) / peak * 100, 1) if peak else 0.0,
        limit_w=topology.phase_limit_w(devices),
    )


@venue_router.get("/devices/{device_id}/trace", response_model=schemas.TraceRead)
async def trace_device_venue(
    venue_id: UUID,
    device_id: UUID,
    direction: str = Query(pattern="^(upstream|downstream)$"),
    signal: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> schemas.TraceRead:
    """Trace a device in a venue's base rig (same as the job route, scoped by venue)."""
    await _venue_device(db, venue_id, device_id)
    edges = await _venue_all_edges(db, venue_id)
    devices = {str(d.id): _as_dict(d) for d in await _venue_all_devices(db, venue_id)}
    result = topology.trace([_as_dict(e) for e in edges], str(device_id), direction, signal=signal)
    by_id = {str(e.id): e for e in edges}
    issues = [
        i
        for hop in result.hops
        for i in topology.validate_edge(
            _as_dict(by_id[str(hop.edge["id"])]),
            devices.get(str(hop.edge["src_device_id"])),
            devices.get(str(hop.edge["dst_device_id"])),
            [_as_dict(e) for e in edges],
        )
    ]
    return schemas.TraceRead(
        root=result.root,
        direction=direction,
        truncated=result.truncated,
        hops=[
            schemas.HopRead(
                depth=h.depth,
                device_id=h.device_id,
                edge=schemas.ConnectionEdgeRead.model_validate(by_id[str(h.edge["id"])]),
            )
            for h in result.hops
        ],
        issues=[schemas.IssueRead(**vars(i)) for i in issues],
    )
