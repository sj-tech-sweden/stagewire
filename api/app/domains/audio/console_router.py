"""Digital-console endpoints: profile, bus budget, stereo links, soft patch, fader map, accessories.

All routes sit under ``/jobs/{job_id}/...`` next to the audio router. Writes go through
``console_service`` so the pairing and budget invariants hold, then publish the changed nodes like
every other audio write.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.audio import console, console_service, schemas, service
from app.domains.audio.ws import publish_job_event
from app.domains.auth.deps import get_current_user
from app.domains.graph import audio_native
from app.domains.graph.mirror import MirrorToGraphRoute
from app.domains.stockwire.client import StockwireClient
from app.domains.stockwire.config import load_integration_config

router = APIRouter(
    prefix="/jobs",
    tags=["audio:console"],
    dependencies=[Depends(get_current_user)],
    route_class=MirrorToGraphRoute,
)


class ConsoleProfileSet(BaseModel):
    """Exactly one of the four ways to set a console's profile."""

    preset: str | None = None
    profile: dict | None = None
    from_stockwire: bool = False
    clear: bool = False


class LinkRequest(BaseModel):
    primary_channel_id: UUID
    secondary_channel_id: UUID | None = None


class SocketRef(BaseModel):
    device_id: UUID
    port_id: str
    socket: int = Field(default=1, ge=1)


class AccessoryPick(BaseModel):
    product_id: int
    name: str = ""
    quantity: int = Field(default=1, ge=1)


async def _require_list(db: AsyncSession, job_id: UUID, list_id: UUID):
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    row = await service.get_channel_list(db, list_id, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel list not found")
    return row


def _channel_dict(channel: Any) -> dict:
    return {
        "id": str(channel.id),
        "channel_number": channel.channel_number or 0,
        "source_label": channel.source_label,
        "is_stereo_linked": bool(channel.is_stereo_linked),
        "stereo_link_role": channel.stereo_link_role,
        "stereo_partner_id": channel.stereo_partner_id,
    }


def _summary(row: Any) -> dict:
    profile = console_service.profile_of(row)
    buses = console_service.buses_of(row.outputs)
    pairs = [
        {"primary": str(c.id), "secondary": c.stereo_partner_id, "channel_number": c.channel_number}
        for c in row.channels
        if c.stereo_link_role == "primary"
    ]
    return {
        "list_id": str(row.id),
        "simple": console.is_simple(profile),
        "profile": profile.model_dump() if profile else None,
        "source": profile.source if profile else "none",
        "budget": console.bus_budget(profile, buses, _effective_fx(row)),
        "links": pairs,
        "dcas": _live_dcas(row, row_strip_ids(row)),
        "dca_count": profile.dcas if profile else 0,
        "fx": _live_fx(row, {str(c.id) for c in row.channels}),
        "fx_capacity": profile.dsp_inputs.fx_returns if profile else 0,
    }


async def _publish_channels(db: AsyncSession, job_id: UUID, nodes: list) -> None:
    await audio_native.publish_nodes(db, job_id, [n.id for n in nodes])
    for node in nodes:
        channel = await service.get_channel(db, audio_native.public_id(node), job_id)
        if channel is not None:
            await publish_job_event(
                job_id, "channel.upsert", schemas.AudioChannelPatchRead.model_validate(channel)
            )


@router.get("/{job_id}/console-presets")
async def console_presets(job_id: UUID) -> list[dict]:
    """Built-in profiles an engineer can pick when the Stockwire product has no ``specs.mixer``."""
    return console.list_presets()


@router.get("/{job_id}/channel-lists/{list_id}/console")
async def get_console(job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Profile (or ``simple``), live bus budget and stereo pairs of one console."""
    return _summary(await _require_list(db, job_id, list_id))


@router.put("/{job_id}/channel-lists/{list_id}/console-profile")
async def set_console_profile(
    job_id: UUID,
    list_id: UUID,
    payload: ConsoleProfileSet,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pick a preset, type a manual profile, re-read Stockwire ``specs.mixer``, or clear to simple.

    A manual profile is validated strictly (422 on a bad value). Reading from Stockwire needs the
    list's mixer product to be set and to carry ``specs.mixer``; otherwise 422 and the engineer
    falls back to a preset or manual entry (spec §5).
    """
    row = await _require_list(db, job_id, list_id)
    chosen = [
        bool(payload.preset),
        payload.profile is not None,
        payload.from_stockwire,
        payload.clear,
    ]
    if sum(chosen) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Send exactly one of preset, profile, from_stockwire or clear",
        )
    stored: dict | None
    if payload.clear:
        stored = None
    elif payload.preset:
        profile = console.preset_profile(payload.preset)
        if profile is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown console preset")
        stored = profile.model_dump()
    elif payload.profile is not None:
        try:
            profile = console.MixerProfile.model_validate({**payload.profile, "source": "manual"})
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        stored = profile.model_dump()
    else:
        stored = await _profile_from_stockwire(db, row)
    updated = await service.update_channel_list(db, row, {"mixer_profile": stored})
    await audio_native.publish_nodes(
        db, job_id, [await audio_native.node_id_of(db, audio_native.LIST, list_id)]
    )
    await publish_job_event(job_id, "list.upsert", schemas.ChannelListRead.model_validate(updated))
    return _summary(updated)


async def _profile_from_stockwire(db: AsyncSession, row: Any) -> dict:
    if not row.mixer_product_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick the console's Stockwire product first"
        )
    # imported lazily: the audio router imports this package's helpers, so a module-level import
    # of it here would be circular
    from app.domains.audio.router import stockwire_product_fetcher

    fetch = await stockwire_product_fetcher(db)
    if fetch is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stockwire integration is not configured")
    try:
        product = await fetch(str(row.mixer_product_id))
    except Exception as exc:  # noqa: BLE001 - upstream failure is reported, not raised
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stockwire lookup failed: {exc}") from exc
    profile = console.parse_mixer_specs(product)
    if profile is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This Stockwire product has no specs.mixer; choose a preset or enter it manually",
        )
    return profile.model_dump()


@router.post("/{job_id}/channel-lists/{list_id}/console/link")
async def link_channels(
    job_id: UUID,
    list_id: UUID,
    payload: LinkRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_list(db, job_id, list_id)
    primary, secondary = await console_service.link_pair(
        db, job_id, list_id, payload.primary_channel_id, payload.secondary_channel_id
    )
    await db.commit()
    await _publish_channels(db, job_id, [primary, secondary])
    return _summary(await service.get_channel_list(db, list_id, job_id))


@router.post("/{job_id}/channel-lists/{list_id}/console/unlink")
async def unlink_channels(
    job_id: UUID,
    list_id: UUID,
    payload: LinkRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _require_list(db, job_id, list_id)
    nodes = await console_service.unlink_pair(db, job_id, payload.primary_channel_id)
    await db.commit()
    await _publish_channels(db, job_id, nodes)
    return _summary(await service.get_channel_list(db, list_id, job_id))


@router.get("/{job_id}/channel-lists/{list_id}/fader-map")
async def get_fader_map(job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Surface layer grid (banks x layers) from the profile; ``enabled`` is False without one."""
    row = await _require_list(db, job_id, list_id)
    return _fader_map(row)


def _fader_map(row: Any) -> dict:
    channels = [_channel_dict(c) for c in row.channels]
    live = {c["id"] for c in channels}
    return console.fader_map(
        console_service.profile_of(row),
        channels,
        console_service.buses_of(row.outputs),
        row.fader_layout,
        _live_fx(row, live),
        _live_dcas(row, row_strip_ids(row)),
    )


def _effective_fx(row: Any) -> list[dict]:
    """The stored (configured) engines plus the console's remaining built-in ones (placeholders)."""
    return console.effective_fx(console_service.profile_of(row), row.fx_config)


def row_strip_ids(row: Any) -> set[str]:
    """Ids a DCA may hold: input strips, FX returns / sends and mixes that still exist."""
    ids = {str(c.id) for c in row.channels if c.stereo_link_role != "secondary"}
    ids |= {console.fx_strip_id(e["id"]) for e in _effective_fx(row)}
    ids |= {console.fx_send_strip_id(e["id"]) for e in _effective_fx(row)}
    ids |= {str(o.id) for o in row.outputs}
    return ids


def _live_fx(row: Any, live_channels: set[str]) -> list[dict]:
    """FX engines minus sends from deleted channels (a delete leaves no stale ids behind)."""
    return [
        {**e, "sends": [c for c in e.get("sends") or [] if c in live_channels]}
        for e in _effective_fx(row)
    ]


def _live_dcas(row: Any, live: set[str]) -> dict:
    return {
        n: {**cfg, "members": [m for m in cfg.get("members") or [] if m in live]}
        for n, cfg in (row.dca_config or {}).items()
    }


class DcaConfigSet(BaseModel):
    # DCA number -> {"name": str, "members": [strip ids]}; replaces the whole configuration
    dcas: dict[str, dict] = Field(default_factory=dict)


class FxEngine(BaseModel):
    id: str
    name: str = ""
    type: str = "reverb"
    stereo_return: bool = True
    send_mode: str = "mono"
    sends: list[UUID] = Field(default_factory=list)


class FxConfigSet(BaseModel):
    fx: list[FxEngine] = Field(default_factory=list)


class FaderLayoutSet(BaseModel):
    # slot key ("layer:bank:fader") -> strip id, "empty", or null; null / omitted = not pinned.
    # ``layout: null`` resets to the default fill.
    layout: dict[str, str | None] | None = None


class FaderAutofill(BaseModel):
    # all = start over from the default fill (the reset); missing = place only unplaced strips
    mode: str = Field(default="all", pattern="^(all|missing)$")


class FaderAdd(BaseModel):
    strip_ids: list[str] = Field(min_length=1)
    # put another copy of a strip that is already on the surface on the next free fader
    duplicate: bool = False


@router.post("/{job_id}/channel-lists/{list_id}/fader-layout/autofill")
async def autofill_faders(
    job_id: UUID,
    list_id: UUID,
    payload: FaderAutofill | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lay the faders out from the default fill and store it, so it is yours from then on.

    ``all`` (default) starts over; ``missing`` only places strips that are on no fader yet.
    """
    row = await _require_list(db, job_id, list_id)
    channels = [_channel_dict(c) for c in row.channels]
    live = {c["id"] for c in channels}
    try:
        layout = console.fader_autofill(
            console_service.profile_of(row),
            channels,
            console_service.buses_of(row.outputs),
            row.fader_layout,
            _live_fx(row, live),
            _live_dcas(row, row_strip_ids(row)),
            payload.mode if payload else "all",
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    updated = await _store(db, job_id, list_id, row, {"fader_layout": layout or None})
    return _fader_map(updated)


@router.post("/{job_id}/channel-lists/{list_id}/fader-layout/add")
async def add_to_faders(
    job_id: UUID,
    list_id: UUID,
    payload: FaderAdd,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Put strips (typically the hidden built-in FX) on the first free faders in one step.

    Everything currently auto-placed is pinned where it is, so adding never shuffles the surface;
    the layout becomes custom. 422 when a strip is unknown or the surface is full.
    """
    row = await _require_list(db, job_id, list_id)
    channels = [_channel_dict(c) for c in row.channels]
    live = {c["id"] for c in channels}
    try:
        layout = console.fader_add(
            console_service.profile_of(row),
            channels,
            console_service.buses_of(row.outputs),
            row.fader_layout,
            _live_fx(row, live),
            _live_dcas(row, row_strip_ids(row)),
            payload.strip_ids,
            payload.duplicate,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    updated = await _store(db, job_id, list_id, row, {"fader_layout": layout})
    return _fader_map(updated)


@router.put("/{job_id}/channel-lists/{list_id}/fader-layout")
async def set_fader_layout(
    job_id: UUID,
    list_id: UUID,
    payload: FaderLayoutSet,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pin strips to fader slots (the full layout is replaced); ``null`` resets to the default."""
    row = await _require_list(db, job_id, list_id)
    stored: dict | None = None
    if payload.layout is not None:
        profile = console_service.profile_of(row)
        # the same strip set the map shows: inputs, FX returns, mixes, FX sends and named DCAs
        # (a layout may pin any of them, so validating against fewer would reject a pin of an FX)
        ids = {
            s["id"]
            for s in console.fader_strips(
                profile,
                [_channel_dict(c) for c in row.channels],
                console_service.buses_of(row.outputs),
                _live_fx(row, {str(c.id) for c in row.channels}),
                _live_dcas(row, row_strip_ids(row)),
            )
        }
        try:
            stored = console.validate_fader_layout(profile, payload.layout, ids) or None
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    updated = await service.update_channel_list(db, row, {"fader_layout": stored})
    await audio_native.publish_nodes(
        db, job_id, [await audio_native.node_id_of(db, audio_native.LIST, list_id)]
    )
    await publish_job_event(job_id, "list.upsert", schemas.ChannelListRead.model_validate(updated))
    return _fader_map(updated)


class BulkAssignment(BaseModel):
    # the channel (or, for ``out_socket``, the bus) to set; a null ``ref`` clears it
    channel_id: UUID | None = None
    bus_id: UUID | None = None
    ref: SocketRef | None = None


class BulkSoftPatch(BaseModel):
    assignments: list[BulkAssignment]
    append: bool = False
    field: str = Field(default="dsp_source", pattern="^(dsp_source|direct_out|out_socket)$")


class BusEndpoint(BaseModel):
    # one endpoint of a bus: a single socket (mono) or its first socket (stereo / LCR follow on)
    # ... or the full list of refs when the sockets are not adjacent
    refs: list[SocketRef] = Field(min_length=1, max_length=3)


class BusPatch(BaseModel):
    endpoints: list[BusEndpoint] = Field(default_factory=list)
    append: bool = False


class AutoPatch(BaseModel):
    # channels for ``dsp_source`` (inputs) and ``direct_out``; buses for ``out_socket``
    channel_ids: list[UUID] = Field(default_factory=list)
    bus_ids: list[UUID] = Field(default_factory=list)
    field: str = Field(default="dsp_source", pattern="^(dsp_source|direct_out|out_socket)$")
    device_id: UUID
    port_id: str
    start_socket: int = Field(default=1, ge=1)
    skip_taken: bool = True
    dry_run: bool = False
    # add the planned endpoint to a bus's existing ones instead of replacing them
    append: bool = False
    # let input sockets that other strips already use be reused (a split source)
    allow_shared: bool = False


class ExpansionCard(BaseModel):
    protocol: str
    channels_in: int = Field(default=0, ge=0)
    channels_out: int = Field(default=0, ge=0)


class ExpansionSet(BaseModel):
    installed: list[ExpansionCard] = Field(default_factory=list)


@router.get("/{job_id}/channel-lists/{list_id}/soft-patch")
async def get_soft_patch(job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Every audio socket on the job's hardware, and which DSP strip uses it (input / direct out).

    Sockets come from *any* device on the graph, so a stagebox or Dante card added to the job shows
    up here immediately. A strip pointing at a socket that no longer exists (device removed or
    swapped for one with fewer sockets) is flagged ``orphaned`` instead of silently dropped.
    """
    row = await _require_list(db, job_id, list_id)
    hardware = await console_service.job_hardware(db, job_id)
    sockets = console.audio_sockets(hardware)
    by_key = {s["key"]: s for s in sockets}
    channel_nodes = await console_service.job_channel_nodes(db, job_id)
    nodes = {str(audio_native.public_id(n)): n for n in channel_nodes}
    strips = []
    for channel in row.channels:
        node = nodes.get(str(channel.id))
        entry = {**_channel_dict(channel)}
        for field in ("dsp_source", "direct_out"):
            ref = getattr(channel, field)
            entry[field] = ref
            keys = console_service.occupied(ref, node) if (ref and node) else []
            entry[f"{field}_orphaned"] = bool(ref) and any(k not in by_key for k in keys)
            for key in keys:
                if key in by_key:
                    by_key[key].setdefault(f"{field}_channel_ids", []).append(str(channel.id))
                    by_key[key].setdefault(f"{field}_channel_id", str(channel.id))
        strips.append(entry)
    # an input socket feeding several strips is a split source: flag it so the UI can hint at it
    for socket in sockets:
        socket["shared"] = len(socket.get("dsp_source_channel_ids") or []) > 1
    numbers = {c["id"]: c["channel_number"] for c in strips}
    for entry in strips:
        key = console.socket_key(entry["dsp_source"])
        entry["shared_with"] = [
            {"channel_id": other, "channel_number": numbers.get(other)}
            for other in (by_key.get(key, {}).get("dsp_source_channel_ids") or [])
            if other != entry["id"]
        ]
    used: dict[tuple[str, str], int] = {}
    for socket in sockets:
        if socket.get("dsp_source_channel_id") or socket.get("direct_out_channel_id"):
            key = (socket["device_id"], socket["port_id"])
            used[key] = used.get(key, 0) + 1
    ports: dict[tuple[str, str], dict] = {}
    for socket in sockets:
        key = (socket["device_id"], socket["port_id"])
        entry = ports.setdefault(
            key,
            {
                "device_id": socket["device_id"],
                "device_name": socket["device_name"],
                "port_id": socket["port_id"],
                "direction": socket["direction"],
                "connector": socket["connector"],
                "channels": 0,
            },
        )
        entry["channels"] += 1
    for key, entry in ports.items():
        entry["used"] = used.get(key, 0)
    # ``ports`` is the compact view for big sources (a 128-channel Dante card is one entry, not
    # 128 rows); ``sockets`` stays for exact lookups.
    buses = [
        {
            "id": str(o.id),
            "name": o.name,
            "mode": o.mode,
            "role": o.role,
            "out_socket": o.out_socket,
            "out_endpoints": o.out_endpoints or [],
        }
        for o in sorted(row.outputs, key=lambda o: o.position or 0)
    ]
    for bus in buses:
        for endpoint in bus["out_endpoints"]:
            for key in console.endpoint_keys(endpoint):
                if key in by_key:
                    by_key[key]["out_socket_bus_id"] = bus["id"]
                    by_key[key]["out_endpoint_id"] = endpoint["id"]
    return {"sockets": sockets, "ports": list(ports.values()), "channels": strips, "buses": buses}


@router.put("/{job_id}/channels/{channel_id}/soft-patch")
async def set_soft_patch(
    job_id: UUID,
    channel_id: UUID,
    payload: SocketRef | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Map a physical input socket to this DSP strip (body null clears it)."""
    return await _assign(db, job_id, channel_id, "dsp_source", payload)


@router.put("/{job_id}/channels/{channel_id}/direct-out")
async def set_direct_out(
    job_id: UUID,
    channel_id: UUID,
    payload: SocketRef | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Route this DSP strip straight to a physical output socket; takes no bus slot."""
    return await _assign(db, job_id, channel_id, "direct_out", payload)


async def _assign(
    db: AsyncSession, job_id: UUID, channel_id: UUID, field: str, payload: SocketRef | None
) -> dict:
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    node = await console_service.assign_socket(
        db, job_id, channel_id, field, payload.model_dump() if payload else None
    )
    await db.commit()
    await _publish_channels(db, job_id, [node])
    channel = await service.get_channel(db, channel_id, job_id)
    result = _channel_dict(channel) | {field: getattr(channel, field)}
    if field == "dsp_source":
        # not an error: one source may feed several strips (FOH + monitor channels, each with its
        # own processing). The caller shows a hint listing them.
        result["shared_with"] = await console_service.shared_with(
            db, job_id, node, getattr(channel, field)
        )
    return result


# --- Stockwire accessories / expansion cards --------------------------------------------------


def normalize_accessories(payload: Any) -> list[dict]:
    """Stockwire's accessories response as ``{product_id, name, quantity, required}`` rows.

    The endpoint's exact envelope is not pinned down, so this accepts a bare list or an object with
    ``items`` / ``accessories`` / ``results`` / ``data`` and the common field spellings; rows
    without a numeric product id are dropped. Stockwire-rental returns a bare list of
    ``{accessory_product_id, accessory_name, accessory_sku, quantity, required}``.
    """
    if isinstance(payload, dict):
        for key in ("items", "accessories", "results", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        return []
    rows: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        nested = item.get("accessory") if isinstance(item.get("accessory"), dict) else {}
        raw_id = (
            item.get("accessory_product_id")
            or item.get("accessory_id")
            or item.get("product_id")
            or nested.get("id")
            or item.get("id")
        )
        try:
            product_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        try:
            quantity = max(int(item.get("quantity") or item.get("default_quantity") or 1), 1)
        except (TypeError, ValueError):
            quantity = 1
        rows.append(
            {
                "product_id": product_id,
                "name": str(
                    item.get("accessory_name")  # stockwire-rental's own field
                    or item.get("name")
                    or item.get("product_name")
                    or nested.get("name")
                    or ""
                ),
                "sku": str(item.get("accessory_sku") or item.get("sku") or nested.get("sku") or ""),
                "quantity": quantity,
                "required": bool(item.get("required") or item.get("is_required")),
            }
        )
    return rows


@router.get("/{job_id}/channel-lists/{list_id}/accessories")
async def suggested_accessories(
    job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    """Stageboxes / expansion cards Stockwire lists for the console, flagged if already bundled."""
    row = await _require_list(db, job_id, list_id)
    if not row.mixer_product_id:
        return {"suggestions": [], "bundled": row.bundled_accessories or []}
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stockwire integration is not configured")
    sw = StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])
    try:
        raw = await sw.list_product_accessories(row.mixer_product_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stockwire lookup failed: {exc}") from exc
    bundled = {a["product_id"] for a in row.bundled_accessories or []}
    suggestions = [
        {**acc, "bundled": acc["product_id"] in bundled} for acc in normalize_accessories(raw)
    ]
    return {"suggestions": suggestions, "bundled": row.bundled_accessories or []}


@router.put("/{job_id}/channel-lists/{list_id}/accessories")
async def set_bundled_accessories(
    job_id: UUID,
    list_id: UUID,
    payload: list[AccessoryPick],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Replace the hardware bundled with this console; the next Stockwire sync requires them all.

    Duplicate product ids are merged (quantities add up) so a bundle never lists a product twice.
    """
    row = await _require_list(db, job_id, list_id)
    merged: dict[int, dict] = {}
    for pick in payload:
        entry = merged.setdefault(
            pick.product_id, {"product_id": pick.product_id, "name": pick.name, "quantity": 0}
        )
        entry["quantity"] += pick.quantity
        entry["name"] = entry["name"] or pick.name
    updated = await service.update_channel_list(
        db, row, {"bundled_accessories": list(merged.values())}
    )
    await audio_native.publish_nodes(
        db, job_id, [await audio_native.node_id_of(db, audio_native.LIST, list_id)]
    )
    await publish_job_event(job_id, "list.upsert", schemas.ChannelListRead.model_validate(updated))
    return {"bundled": updated.bundled_accessories or []}


@router.get("/{job_id}/channel-lists/{list_id}/propose-mixer")
async def propose_mixer(
    job_id: UUID,
    list_id: UUID,
    category_id: list[int] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Consoles from the Stockwire catalog ranked by how well they cover this list.

    The need is the list's DSP strips plus its buses priced in bus-pool slots (``mixer_need``).
    Two catalog queries are merged: one by input count (finds simple/analog desks too) and one that
    also requires a bus pool of the needed size (finds digital desks a plain input query might rank
    below the page limit). Every candidate is then judged locally with its *own* pool rules
    (``fit_mixer``), so a desk whose odd/even pairing wastes a slot, or that lacks a needed bus
    role, is shown as not fitting with the reason.
    """
    row = await _require_list(db, job_id, list_id)
    channels = [_channel_dict(c) for c in row.channels]
    buses = console_service.buses_of(row.outputs)
    need = console.mixer_need(channels, buses)
    cfg = await load_integration_config(db)
    if not cfg.get("api_key"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stockwire integration is not configured")
    sw = StockwireClient(base_url=cfg["base_url"], token=cfg["api_key"])
    base = {"min_inputs": need["strips"] or None, "limit": limit}
    queries = [dict(base)]
    if need["bus_slots"]:
        queries.append({**base, "min_bus_slots": need["bus_slots"]})
    found: dict[str, dict] = {}
    try:
        for query in queries:
            for category in category_id or [None]:
                page = await sw.search_products(category_id=category, **query)
                for item in page.get("items") or []:
                    found.setdefault(str(item.get("id")), item)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Stockwire lookup failed: {exc}") from exc
    proposals = [
        {
            "product_id": pid,
            "name": item.get("name") or "",
            "sku": item.get("sku"),
            **console.fit_mixer(need, buses, item),
        }
        for pid, item in found.items()
    ]
    return {"need": need, "candidates": console.rank_proposals(proposals)[:limit]}


@router.put("/{job_id}/channel-lists/{list_id}/dcas")
async def set_dcas(
    job_id: UUID, list_id: UUID, payload: DcaConfigSet, db: AsyncSession = Depends(get_db)
) -> dict:
    """Name the console's DCAs and choose what each one controls (replaces the configuration)."""
    row = await _require_list(db, job_id, list_id)
    valid = row_strip_ids(row)
    # A member whose strip is gone since the client loaded its draft is dropped quietly: a deleted
    # channel (it was saved before) or a removed FX engine (its ``fx-`` / ``fxs-`` strips; the FX
    # save already pruned them from the stored DCAs). Any other unknown id is still an error.
    previous = {m for cfg in (row.dca_config or {}).values() for m in cfg.get("members") or []}

    def stale(member: str) -> bool:
        return member not in valid and (member in previous or member.startswith(("fx-", "fxs-")))

    cleaned = {
        n: {**cfg, "members": [m for m in cfg.get("members") or [] if not stale(str(m))]}
        for n, cfg in payload.dcas.items()
    }
    try:
        stored = console.validate_dca_config(console_service.profile_of(row), cleaned, valid)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    updated = await _store(db, job_id, list_id, row, {"dca_config": stored or None})
    return _summary(updated)


@router.put("/{job_id}/channel-lists/{list_id}/fx")
async def set_fx(
    job_id: UUID,
    list_id: UUID,
    payload: FxConfigSet,
    force: bool = Query(False, description="Save even if the FX sends overflow the bus pool"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Configure the console's built-in FX engines and which channels send to each.

    When the console counts FX sends in its bus pool (``fx_send`` among its pool roles) the
    engines' sends are budgeted: a configuration that overflows the pool is refused (409) unless
    ``force``.
    Removing an engine also removes its return / send from every DCA.
    """
    row = await _require_list(db, job_id, list_id)
    profile = console_service.profile_of(row)
    channel_ids = {str(c.id) for c in row.channels if c.stereo_link_role != "secondary"}
    try:
        stored = console.validate_fx_config(
            profile, [{**e.model_dump(mode="json")} for e in payload.fx], channel_ids
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    after_fx = console.effective_fx(profile, stored)
    budget = console.bus_budget(profile, console_service.buses_of(row.outputs), after_fx)
    if not budget["ok"] and not force:
        before = console.bus_budget(
            profile, console_service.buses_of(row.outputs), _effective_fx(row)
        )
        if budget["over_by"] > before["over_by"] or len(budget["violations"]) > len(
            before["violations"]
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"message": "; ".join(budget["violations"]), "budget": budget},
            )
    # engines that no longer exist at all (a built-in one that is merely reset stays on the surface)
    gone = {e["id"] for e in _effective_fx(row)} - {e["id"] for e in after_fx}
    data: dict = {"fx_config": stored or None}
    if gone and row.dca_config:
        dead = {console.fx_strip_id(i) for i in gone} | {console.fx_send_strip_id(i) for i in gone}
        pruned = {
            n: {**cfg, "members": [m for m in cfg.get("members") or [] if m not in dead]}
            for n, cfg in row.dca_config.items()
        }
        data["dca_config"] = {n: c for n, c in pruned.items() if c["name"] or c["members"]} or None
    updated = await _store(db, job_id, list_id, row, data)
    return _summary(updated)


async def _store(db: AsyncSession, job_id: UUID, list_id: UUID, row: Any, data: dict) -> Any:
    updated = await service.update_channel_list(db, row, data)
    await audio_native.publish_nodes(
        db, job_id, [await audio_native.node_id_of(db, audio_native.LIST, list_id)]
    )
    await publish_job_event(job_id, "list.upsert", schemas.ChannelListRead.model_validate(updated))
    return updated


@router.put("/{job_id}/channel-lists/{list_id}/soft-patch/bulk")
async def bulk_soft_patch(
    job_id: UUID,
    list_id: UUID,
    payload: BulkSoftPatch,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set or clear many sockets (inputs, direct outs, bus outputs) at once; all or nothing."""
    row = await _require_list(db, job_id, list_id)
    items = []
    for a in payload.assignments:
        target = a.bus_id if payload.field == "out_socket" else a.channel_id
        if target is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Each assignment needs a bus_id (out_socket) or a channel_id",
            )
        items.append((target, a.ref.model_dump() if a.ref else None))
    nodes = await console_service.assign_many(
        db, job_id, items, payload.field, (list_id, row), payload.append
    )
    await db.commit()
    await _publish_channels(db, job_id, nodes)
    return {"updated": len(nodes)}


@router.post("/{job_id}/channel-lists/{list_id}/soft-patch/auto")
async def auto_soft_patch(
    job_id: UUID,
    list_id: UUID,
    payload: AutoPatch,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Patch channels (inputs, direct outs) or buses, in order, onto consecutive sockets.

    "Ch 1-16 to Dante 1-16", "these 8 direct outs to the AR2412 outs from 5", "Mix 1-8 to Dante out
    1-8". A stereo bus takes two adjacent sockets, an LCR bus three. Sockets used by other strips
    are skipped (or refused with ``skip_taken`` false); the selection's own current sockets count as
    free so re-patching is repeatable. Input sockets may be shared by several strips (a split
    source): with ``allow_shared`` nothing counts as taken. ``dry_run`` returns the plan only; a bus
    plan with ``append`` adds an endpoint to each bus instead of replacing its endpoints.
    """
    row = await _require_list(db, job_id, list_id)
    buses_mode = payload.field == "out_socket"
    ids = payload.bus_ids if buses_mode else payload.channel_ids
    if not ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose at least one bus" if buses_mode else "Choose at least one channel",
        )
    pool = (
        {str(o.id): o for o in row.outputs} if buses_mode else {str(c.id): c for c in row.channels}
    )
    chosen = []
    for item_id in ids:
        item = pool.get(str(item_id))
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{item_id} is not in this list")
        if buses_mode:
            chosen.append(
                {"id": str(item.id), "name": item.name, "width": console.bus_width(item.mode)}
            )
        else:
            chosen.append(_channel_dict(item))
    hardware = await console_service.job_hardware(db, job_id)
    sockets = console.audio_sockets(hardware)
    selected = {str(i) for i in ids}
    taken: set[str | None] = set()
    if payload.field == "dsp_source":
        if not payload.allow_shared:
            for channel in row.channels:
                if channel.dsp_source and str(channel.id) not in selected:
                    taken.add(console.socket_key(channel.dsp_source))
    else:
        # output sockets are exclusive between channel direct outs and bus endpoints
        for channel in row.channels:
            if channel.direct_out and not (
                payload.field == "direct_out" and str(channel.id) in selected
            ):
                taken.add(console.socket_key(channel.direct_out))
        for bus in row.outputs:
            replaced = buses_mode and str(bus.id) in selected and not payload.append
            if not replaced:
                for endpoint in bus.out_endpoints or []:
                    taken.update(console.endpoint_keys(endpoint))
    try:
        plan = console.soft_patch_plan(
            sockets,
            {k for k in taken if k},
            chosen,
            str(payload.device_id),
            payload.port_id,
            payload.start_socket,
            payload.skip_taken,
            "in" if payload.field == "dsp_source" else "out",
            "bus_id" if buses_mode else "channel_id",
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not payload.dry_run:
        key = "bus_id" if buses_mode else "channel_id"
        nodes = await console_service.assign_many(
            db,
            job_id,
            [
                (
                    UUID(p[key]),
                    {"device_id": p["device_id"], "port_id": p["port_id"], "socket": p["socket"]},
                )
                for p in plan
            ],
            payload.field,
            (list_id, row),
            payload.append,
        )
        await db.commit()
        await _publish_channels(db, job_id, nodes)
    return {"plan": plan, "applied": not payload.dry_run}


async def _bus_context(db: AsyncSession, job_id: UUID, output_id: UUID):
    if await service.get_job(db, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Production job not found")
    bus = await service.get_output(db, output_id, job_id)
    if bus is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bus not found")
    return bus, await service.get_channel_list(db, bus.channel_list_id, job_id)


async def _bus_result(db: AsyncSession, job_id: UUID, output_id: UUID, node) -> dict:
    await db.commit()
    await _publish_channels(db, job_id, [node])
    fresh = await service.get_output(db, output_id, job_id)
    return {
        "id": str(output_id),
        "out_socket": fresh.out_socket,
        "out_endpoints": fresh.out_endpoints or [],
    }


@router.put("/{job_id}/outputs/{output_id}/soft-patch")
async def set_bus_socket(
    job_id: UUID,
    output_id: UUID,
    payload: BusPatch | SocketRef | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set where a bus leaves from. A bus may have several endpoints (a stereo bus: L and R per
    endpoint). The body is ``{endpoints: [{refs: [...]}], append}``; a bare socket ref (one mono
    endpoint, or a stereo/LCR bus's first socket) and ``null`` (clear) are also accepted."""
    bus, row = await _bus_context(db, job_id, output_id)
    append = False
    if payload is None:
        endpoints: list[list[dict]] = []
    elif isinstance(payload, SocketRef):
        endpoints = [[payload.model_dump()]]
    else:
        endpoints = [[r.model_dump() for r in e.refs] for e in payload.endpoints]
        append = payload.append
    node = await console_service.assign_output_endpoints(
        db, job_id, output_id, bus.channel_list_id, row, endpoints, append=append
    )
    return await _bus_result(db, job_id, output_id, node)


@router.delete("/{job_id}/outputs/{output_id}/soft-patch/{endpoint_id}")
async def remove_bus_endpoint(
    job_id: UUID, output_id: UUID, endpoint_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Remove one endpoint of a bus (the others stay)."""
    bus, row = await _bus_context(db, job_id, output_id)
    node = await console_service.remove_output_endpoint(
        db, job_id, output_id, bus.channel_list_id, row, endpoint_id
    )
    return await _bus_result(db, job_id, output_id, node)


@router.get("/{job_id}/channel-lists/{list_id}/expansion")
async def get_expansion(job_id: UUID, list_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Expansion ports the console offers (Stockwire, preset or typed in) and what is fitted."""
    row = await _require_list(db, job_id, list_id)
    profile = console_service.profile_of(row)
    return {
        "available": [p.model_dump() for p in profile.expansion_ports] if profile else [],
        "installed": row.expansion_installed or [],
    }


@router.put("/{job_id}/channel-lists/{list_id}/expansion")
async def set_expansion(
    job_id: UUID,
    list_id: UUID,
    payload: ExpansionSet,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fit expansion cards: each becomes real sockets on the console device for the soft patch.

    The console device is created if the list has none yet. Removing a card that strips are patched
    through leaves those strips pointing at sockets that no longer exist; the next graph sync
    clears them (the chain is the source of truth), so the card cannot be removed from under a
    patch silently: it is refused with the channels it would orphan.
    """
    row = await _require_list(db, job_id, list_id)
    profile = console_service.profile_of(row)
    try:
        clean = console.validate_expansion(profile, [c.model_dump() for c in payload.installed])
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    node = await console_service.console_device(db, job_id, list_id, row)
    still_there = console_service.expansion_port_ids(node, clean)

    def uses_missing(ref: dict | None) -> bool:
        return (
            bool(ref)
            and str(ref.get("device_id")) == str(node.id)
            and (ref.get("port_id") not in still_there)
        )

    in_use = [
        f"Ch {c.channel_number}"
        for c in row.channels
        if uses_missing(c.dsp_source) or uses_missing(c.direct_out)
    ] + [
        f"bus {o.name}"
        for o in row.outputs
        if any(uses_missing(r) for e in o.out_endpoints or [] for r in e.get("refs") or [])
    ]
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ports still in use by " + ", ".join(in_use[:8]) + ": clear their patch first",
        )
    await console_service.apply_expansion(db, node, clean)
    updated = await service.update_channel_list(db, row, {"expansion_installed": clean or None})
    await db.commit()
    await audio_native.publish_nodes(
        db, job_id, [await audio_native.node_id_of(db, audio_native.LIST, list_id), node.id]
    )
    await publish_job_event(job_id, "list.upsert", schemas.ChannelListRead.model_validate(updated))
    return {"installed": clean, "device_id": str(node.id)}
