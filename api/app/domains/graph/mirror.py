import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as db_mod
from app.domains.audio import schemas as audio_schemas
from app.domains.audio import service
from app.domains.audio.models import ProductionJob
from app.domains.audio.ws import publish_job_event
from app.domains.graph.backfill import CHANNEL_FIELDS, OUTPUT_FIELDS, backfill_job
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.video import service as video_service

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


async def sync_job_to_graph(job_id: UUID) -> None:
    """Bring the graph up to date with a job's legacy rows (own session, never raises)."""
    try:
        async with db_mod.SessionLocal() as db:
            if await db.get(ProductionJob, job_id) is None:
                return
            await backfill_job(db, job_id)
    except Exception:  # noqa: BLE001 - the legacy write already succeeded; the next read heals
        logger.exception("graph sync failed for job %s", job_id)


class MirrorToGraphRoute(APIRoute):
    """After a successful legacy write under /jobs/{job_id}/..., sync that job into the graph."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await original(request)
            raw = request.path_params.get("job_id")
            if raw and request.method in WRITE_METHODS and response.status_code < 300:
                try:
                    job_id = UUID(str(raw))
                except ValueError:
                    return response
                await sync_job_to_graph(job_id)
            return response

        return handler


# --- graph -> legacy ---------------------------------------------------------------------
# PATCH/DELETE on a graph twin of a legacy channel list, channel, output, audio device or patch
# point is written through to the legacy row (same services the legacy editors use) so both
# editors and every unmoved reader stay consistent. Graph-only fields (canvas position, cable
# label, phase) are never mirrored.

CHANNEL_NOT_NULL = {"channel_number", "stand_type", "instrument_group", "phantom_power", "stereo"}
DEVICE_ATTRS = {
    "power_w": "power_watts",
    "weight_kg": "weight_kg",
    "input_override": "input_override",
    "output_override": "output_override",
    "fixture_type": "fixture_type",
    "channel_mode": "channel_mode",
    "footprint_channels": "footprint_channels",
    "default_gel": "default_gel",
}
POINT_KEYS = ("connector", "patch_label", "notes")


def legacy_target(row: GraphDevice | ConnectionEdge) -> tuple[str, UUID] | None:
    ref = getattr(row, "legacy_ref", None)
    if ref is None and isinstance(row, ConnectionEdge):
        ref = (row.attributes or {}).get("legacy_ref")
    table, _, raw = (ref or "").partition(":")
    try:
        return table, UUID(raw)
    except ValueError:
        return None


def _channel_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if "name" in data:
        out["source_label"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    if "position" in data and "channel_number" not in attrs:
        out["channel_number"] = data["position"]
    for key in CHANNEL_FIELDS:
        if key in attrs and not (attrs[key] is None and key in CHANNEL_NOT_NULL):
            out[key] = attrs[key]
    for key in ("stockwire_product_id", "stockwire_product_name"):
        if key in data:
            out[key] = data[key]
    return out


def _list_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    for key in ("name", "position"):
        if key in data and data[key] is not None:
            out[key] = data[key]
    for key in ("mixer_product_id", "mixer_product_name", "mixer_inputs", "mixer_buses"):
        if key in attrs:
            out[key] = attrs[key]
    if "stockwire_product_id" in data and "mixer_product_id" not in attrs:
        out["mixer_product_id"] = data["stockwire_product_id"]
    if "stockwire_product_name" in data and "mixer_product_name" not in attrs:
        out["mixer_product_name"] = data["stockwire_product_name"]
    return out


def _output_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    for key in ("name", "position"):
        if key in data and data[key] is not None:
            out[key] = data[key]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    for key in OUTPUT_FIELDS:
        if key in attrs and not (key == "mode" and attrs[key] is None):
            out[key] = attrs[key]
    return out


def _audio_device_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if "name" in data and data["name"] is not None:
        out["name"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    if "position" in data and data["position"] is not None:
        out["position"] = data["position"]
    if data.get("kind"):
        out["device_type"] = data["kind"]
    elif attrs.get("device_type"):
        out["device_type"] = attrs["device_type"]
    for graph_key, column in DEVICE_ATTRS.items():
        if graph_key in attrs:
            out[column] = attrs[graph_key]
    for key in ("stockwire_product_id", "stockwire_product_name"):
        if key in data:
            out[key] = data[key]
    return out


async def device_to_legacy(db: AsyncSession, job_id: UUID, device: GraphDevice, data: dict) -> bool:
    """Write a graph device PATCH through to its legacy row. True when a legacy row changed."""
    target = legacy_target(device)
    if target is None:
        return False
    table, legacy_id = target
    if table == "audio_channel_patches":
        row, changes = await service.get_channel(db, legacy_id), _channel_changes(data)
        if row is None or not changes:
            return False
        row = await service.update_channel(db, row, changes)
        read = audio_schemas.AudioChannelPatchRead.model_validate(
            await service.get_channel(db, legacy_id)
        )
        await publish_job_event(job_id, "channel.upsert", read)
    elif table == "audio_channel_lists":
        row, changes = await service.get_channel_list(db, legacy_id), _list_changes(data)
        if row is None or not changes:
            return False
        await service.update_channel_list(db, row, changes)
        await _publish_list(db, job_id, legacy_id)
    elif table == "channel_list_outputs":
        row, changes = await service.get_output(db, legacy_id), _output_changes(data)
        if row is None or not changes:
            return False
        await service.update_output(db, row, changes)
        await _publish_list(db, job_id, row.channel_list_id)
    elif table == "audio_devices":
        row, changes = await service.get_device(db, legacy_id), _audio_device_changes(data)
        if row is None or not changes:
            return False
        row = await service.update_device(db, row, changes)
        from app.domains.audio.router import _device_read

        await publish_job_event(job_id, "device.upsert", await _device_read(db, row))
    else:
        return False
    return True


async def _publish_list(db: AsyncSession, job_id: UUID, list_id: UUID) -> None:
    lst = await service.get_channel_list(db, list_id)
    if lst is not None:
        await publish_job_event(
            job_id, "list.upsert", audio_schemas.ChannelListRead.model_validate(lst)
        )


async def delete_device_twin(db: AsyncSession, job_id: UUID, device: GraphDevice) -> bool:
    """Delete the legacy row behind a graph device (checked first, so the caller can abort)."""
    target = legacy_target(device)
    if target is None:
        return False
    table, legacy_id = target
    if table == "audio_channel_patches":
        row = await service.get_channel(db, legacy_id)
        if row is None:
            return False
        await service.delete_channel(db, row)
        await publish_job_event(job_id, "channel.delete", {"id": str(legacy_id)})
    elif table == "audio_channel_lists":
        row = await service.get_channel_list(db, legacy_id)
        if row is None:
            return False
        await service.delete_channel_list(db, row)
        await publish_job_event(job_id, "list.delete", {"id": str(legacy_id)})
    elif table == "channel_list_outputs":
        row = await service.get_output(db, legacy_id)
        if row is None:
            return False
        list_id = row.channel_list_id
        await service.delete_output(db, row)
        await _publish_list(db, job_id, list_id)
    elif table == "audio_devices":
        row = await service.get_device(db, legacy_id)
        if row is None:
            return False
        if (
            row.patch_points
            or row.output_points
            or await video_service.device_has_patch_points(db, legacy_id)
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Move or delete the patch points on this device before removing it",
            )
        await service.delete_device(db, row)
        await publish_job_event(job_id, "device.delete", {"id": str(legacy_id)})
    else:
        return False
    return True


def _point_changes(attrs: dict) -> dict:
    return {key: attrs[key] for key in POINT_KEYS if key in attrs}


async def edge_to_legacy(db: AsyncSession, job_id: UUID, edge: ConnectionEdge, data: dict) -> bool:
    """Write patch-point fields of an edge PATCH (connector, label, notes) to the legacy point."""
    target = legacy_target(edge)
    attrs = data.get("attributes") or {}
    if target is None or not attrs:
        return False
    table, legacy_id = target
    if table == "channel_patch_points":
        point, changes = await service.get_patch_point(db, legacy_id), _point_changes(attrs)
        if point is None or not changes:
            return False
        await service.update_patch_point(db, point, changes)
        channel = await service.get_channel(db, point.channel_id)
        await publish_job_event(
            job_id, "channel.upsert", audio_schemas.AudioChannelPatchRead.model_validate(channel)
        )
    elif table in ("output_patch_points", "channel_list_outputs"):
        if table == "channel_list_outputs":
            first = attrs.get("first_point") or (edge.attributes or {}).get("first_point") or {}
            changes = _point_changes(attrs.get("first_point") or {})
            point_id = first.get("point_id")
            point = await service.get_output_point(db, UUID(point_id)) if point_id else None
        else:
            changes = _point_changes(attrs)
            point = await service.get_output_point(db, legacy_id)
        if point is None or not changes:
            return False
        await service.update_output_point(db, point, changes)
        output = await service.get_output(db, point.output_id)
        await _publish_list(db, job_id, output.channel_list_id)
    else:
        return False
    return True


async def delete_edge_twin(db: AsyncSession, job_id: UUID, edge: ConnectionEdge) -> bool:
    target = legacy_target(edge)
    if target is None:
        return False
    table, legacy_id = target
    if table == "channel_patch_points":
        point = await service.get_patch_point(db, legacy_id)
        if point is None:
            return False
        channel_id = point.channel_id
        await service.delete_patch_point(db, point)
        channel = await service.get_channel(db, channel_id)
        await publish_job_event(
            job_id, "channel.upsert", audio_schemas.AudioChannelPatchRead.model_validate(channel)
        )
        return True
    if table in ("output_patch_points", "channel_list_outputs"):
        point_id = (
            legacy_id
            if table == "output_patch_points"
            else (edge.attributes or {}).get("first_point", {}).get("point_id")
        )
        point = await service.get_output_point(db, UUID(str(point_id))) if point_id else None
        if point is None:
            return False
        output = await service.get_output(db, point.output_id)
        await service.delete_output_point(db, point)
        await _publish_list(db, job_id, output.channel_list_id)
        return True
    return False
