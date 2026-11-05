"""Venue-scoped graph sub-API: channel lists, channels, outputs, chains and WWB.

The venue Standard Base Rig reuses the job graph editing UX, so a venue needs the same
incremental list/channel/device operations a job has. Rather than overload the job graph
router, these routes are the venue counterpart of ``app.domains.graph.lists`` and the
WWB endpoints in ``router.py``, keyed by ``venue_id`` instead of ``job_id``.

Deliberate difference from the job routes: venues intentionally skip the job-only mirroring
machinery (backfill, legacy shadow writes, ``publish_job_event``). A venue rig is edited
through these endpoints and the whole-graph ``PUT /venues/{venue_id}/graph``; there is no
separate legacy table to keep in sync and no per-job websocket to notify.
"""

import xml.etree.ElementTree as ET
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import wwb_store
from app.domains.audio.exports import get_exporter
from app.domains.audio.wwb import match_wireless_rows, parse_wwb_show_file
from app.domains.auth.deps import get_current_user
from app.domains.graph import audio_native, readers, schemas
from app.domains.graph.lists import (
    Chain,
    ChainRead,
    ChannelCreate,
    ListCreate,
    OutputCreate,
)
from app.domains.graph.models import GraphDevice

router = APIRouter(
    prefix="/venues/{venue_id}/graph",
    tags=["graph:venue"],
    dependencies=[Depends(get_current_user)],
)

MAX_BATCH = 200
_WWB_WIRELESS_FIELDS = ("wireless_frequency_mhz", "wireless_group", "wireless_channel")


async def _require_venue(db: AsyncSession, venue_id: UUID) -> None:
    from app.domains.venues import service as venue_service

    if await venue_service.get_venue(db, venue_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")


async def _node(db: AsyncSession, venue_id: UUID, node_id: UUID, kind: str) -> GraphDevice:
    node = await db.get(GraphDevice, node_id)
    if node is None or node.venue_id != venue_id or node.kind != kind:
        label = kind.replace("_", " ").title()
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return node


@router.post("/lists", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_list(
    venue_id: UUID, payload: ListCreate, db: AsyncSession = Depends(get_db)
) -> schemas.GraphDeviceRead:
    await _require_venue(db, venue_id)
    existing = (
        await db.scalars(
            select(GraphDevice).where(
                GraphDevice.venue_id == venue_id, GraphDevice.kind == audio_native.LIST
            )
        )
    ).all()
    data = {**payload.model_dump(exclude_unset=True), "position": len(existing)}
    row = await audio_native.create_list(db, venue_id=venue_id, data=data)
    await db.commit()
    node = await db.get(GraphDevice, row.id)
    await db.refresh(node)
    return schemas.GraphDeviceRead.model_validate(node)


async def _members(
    db: AsyncSession, venue_id: UUID, list_node: GraphDevice, kind: str
) -> list[GraphDevice]:
    rows = (
        await db.scalars(
            select(GraphDevice).where(GraphDevice.venue_id == venue_id, GraphDevice.kind == kind)
        )
    ).all()
    return sorted(
        (r for r in rows if (r.attributes or {}).get("list_id") == str(list_node.id)),
        key=lambda r: (r.position, r.created_at),
    )


@router.post(
    "/lists/{list_id}/channels/batch",
    response_model=list[schemas.GraphDeviceRead],
    status_code=201,
)
async def create_channels(
    venue_id: UUID,
    list_id: UUID,
    payload: list[ChannelCreate],
    db: AsyncSession = Depends(get_db),
) -> list[schemas.GraphDeviceRead]:
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} channels")
    list_node = await _node(db, venue_id, list_id, audio_native.LIST)
    existing = await _members(db, venue_id, list_node, audio_native.CHANNEL)
    next_number = max((c.position for c in existing), default=0) + 1
    created: list[GraphDevice] = []
    for item in payload:
        data = item.model_dump(exclude_unset=True)
        if data.get("channel_number") is None:
            data["channel_number"] = next_number
        next_number = max(next_number, data["channel_number"]) + 1
        # job_id is None: channel_node derives the venue scope from the list node.
        node = audio_native.channel_node(None, list_node, data)
        db.add(node)
        created.append(node)
    await db.flush()
    for node in created:
        await audio_native.plot_native_performer(db, node)
    await db.commit()
    return [schemas.GraphDeviceRead.model_validate(node) for node in created]


@router.post(
    "/lists/{list_id}/outputs/batch",
    response_model=list[schemas.GraphDeviceRead],
    status_code=201,
)
async def create_outputs(
    venue_id: UUID,
    list_id: UUID,
    payload: list[OutputCreate],
    db: AsyncSession = Depends(get_db),
) -> list[schemas.GraphDeviceRead]:
    if len(payload) > MAX_BATCH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_BATCH} outputs")
    list_node = await _node(db, venue_id, list_id, audio_native.LIST)
    position = len(await _members(db, venue_id, list_node, audio_native.OUTPUT))
    created: list[GraphDevice] = []
    for offset, item in enumerate(payload):
        node = audio_native.output_node(
            None, list_node, item.model_dump(exclude_unset=True), position + offset
        )
        db.add(node)
        created.append(node)
    await db.commit()
    return [schemas.GraphDeviceRead.model_validate(node) for node in created]


@router.post("/lists/{list_id}/outputs", response_model=schemas.GraphDeviceRead, status_code=201)
async def create_output(
    venue_id: UUID,
    list_id: UUID,
    payload: OutputCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.GraphDeviceRead:
    return (await create_outputs(venue_id, list_id, [payload], db))[0]


@router.put("/channels/{channel_id}/chain", response_model=ChainRead)
async def replace_channel_chain(
    venue_id: UUID,
    channel_id: UUID,
    payload: Chain,
    db: AsyncSession = Depends(get_db),
) -> ChainRead:
    node = await _node(db, venue_id, channel_id, audio_native.CHANNEL)
    points = [
        audio_native.new_point(position, step.device_id, step.point_type or "other", step)
        for position, step in enumerate(payload.steps)
    ]
    await audio_native.replace_points(db, node, points)
    await db.commit()
    return ChainRead(edges=[])


@router.put("/outputs/{output_id}/chain", response_model=ChainRead)
async def replace_output_chain(
    venue_id: UUID,
    output_id: UUID,
    payload: Chain,
    db: AsyncSession = Depends(get_db),
) -> ChainRead:
    node = await _node(db, venue_id, output_id, audio_native.OUTPUT)
    points = [
        audio_native.new_point(
            position, step.device_id, step.point_type or "other", step, output=True
        )
        for position, step in enumerate(payload.steps)
    ]
    await audio_native.replace_points(db, node, points)
    await db.commit()
    return ChainRead(edges=[])


@router.get("/lists/{list_id}/export")
async def export_list(
    venue_id: UUID,
    list_id: UUID,
    plugin: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Console export of a venue channel list (same plugins as the job export)."""
    await _require_venue(db, venue_id)
    exporter = get_exporter(plugin)
    if exporter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown export plugin")
    view = await readers.load_channel_list(db, venue_id=venue_id, list_id=list_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    stored = await wwb_store.get_show_file(db, list_id)
    if stored is not None:
        view[0].wwb_show_file_content = stored
    result = exporter.export(*view)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post("/lists/{list_id}/wireless-workbench/parse")
async def parse_wireless_workbench(
    venue_id: UUID,
    list_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Preview a Shure Wireless Workbench ``.shw`` before importing onto a venue list."""
    await _require_venue(db, venue_id)
    raw = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_wwb_show_file(raw)
    except ET.ParseError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid Wireless Workbench file: {exc}"
        ) from exc
    view = await readers.load_channel_list(db, venue_id=venue_id, list_id=list_id)
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
    venue_id: UUID,
    list_id: UUID,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Import a Shure Wireless Workbench ``.shw`` onto a venue list's wireless channels.

    Mirrors the job import: the file is parsed and matched to the list's wireless channels
    (by name or order), the coordinated frequencies are written back, and the file is stored
    against the venue so it can later be re-exported. No per-job websocket is published.
    """
    await _require_venue(db, venue_id)
    raw = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_wwb_show_file(raw)
    except ET.ParseError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Invalid Wireless Workbench file: {exc}"
        ) from exc
    view = await readers.load_channel_list(db, venue_id=venue_id, list_id=list_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    _, channels, _ = view
    wireless_by_id = {c.id: c for c in channels if getattr(c, "input_type", None) == "wireless"}

    pairs: list[tuple] = []
    if mapping:
        import json

        try:
            mapping_list = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Invalid mapping JSON: {exc}"
            ) from exc
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
        await audio_native.update_channel(db, channel.id, data, venue_id=venue_id)
        updated_ids.append(channel.id)
    await wwb_store.upsert_show_file(
        db, list_id, raw, file.filename or "show.shw", venue_id=venue_id
    )
    await db.commit()
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
