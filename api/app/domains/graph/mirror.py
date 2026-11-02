import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as db_mod
from app.domains.audio import schemas as audio_schemas
from app.domains.audio import service
from app.domains.audio.models import ProductionJob, StagePlotElement
from app.domains.audio.ws import publish_job_event
from app.domains.graph.backfill import (
    CHANNEL_FIELDS,
    DEVICE_SPEC_FIELDS,
    ELEMENT_FIELDS,
    ELEMENT_LINKS,
    FIXTURE_ATTRS,
    MIRRORED_EDGE_TABLES,
    OUTPUT_FIELDS,
    OWNED_ATTRS,
    backfill_job,
)
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.lighting import service as lighting_service
from app.domains.lighting.models import DmxStep, DmxUniverse
from app.domains.video import service as video_service
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
)

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
    "power_inlet": "power_inlet",
    **{key: key for key in DEVICE_SPEC_FIELDS},
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


async def _video_input_points(db, job_id: UUID, device_id: UUID) -> bool:
    # imported here: video_readers imports this module for legacy_target
    from app.domains.graph.video_readers import device_has_video_input_points

    return await device_has_video_input_points(db, job_id, device_id)


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


VIDEO_POINT_KEYS = ("connector", "patch_label", "notes", "source_port", "input_port")


def _video_list_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if data.get("name") is not None:
        out["name"] = data["name"]
    if data.get("position") is not None:
        out["position"] = data["position"]
    for key in (
        "switcher_product_id",
        "switcher_product_name",
        "switcher_inputs",
        "switcher_outputs",
    ):
        if key in attrs:
            out[key] = attrs[key]
    return out


def _video_input_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if data.get("name") is not None and "source_label" not in attrs:
        out["source_label"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    if data.get("position") is not None and "input_number" not in attrs:
        out["input_number"] = max(1, data["position"])
    for key in ("input_number", "source_type", "source_label", "connector"):
        if attrs.get(key) is not None:
            out[key] = attrs[key]
    for key in ("stockwire_product_id", "stockwire_product_name"):
        if key in attrs:
            out[key] = attrs[key]
    return out


def _video_output_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if data.get("name") is not None and "destination_label" not in attrs:
        out["destination_label"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    if data.get("position") is not None and "output_number" not in attrs:
        out["output_number"] = max(1, data["position"])
    for key in ("output_number", "name", "destination_label", "connector"):
        if attrs.get(key) is not None:
            out[key] = attrs[key]
    return out


async def _video_row(db: AsyncSession, job_id: UUID, model, legacy_id: UUID):
    row = await db.get(model, legacy_id)
    if row is None:
        return None
    list_id = row.id if model is VideoInputList else row.list_id
    lst = row if model is VideoInputList else await db.get(VideoInputList, list_id)
    return row if lst is not None and lst.job_id == job_id else None


ELEMENT_NOT_NULL = {
    "element_type",
    "width_cm",
    "height_cm",
    "image_url",
    "coverage_angle_h",
    "coverage_distance_m",
    "power_connector",
}
CANVAS_TO_ELEMENT = {
    "canvas_x_cm": "position_x",
    "canvas_y_cm": "position_y",
    "canvas_rotation": "rotation",
}


def _element_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if "name" in data and data["name"] is not None:
        out["label"] = data["name"]
    if "label" in attrs and data.get("name") is None:
        out["label"] = attrs["label"] or ""
    for graph_key, column in CANVAS_TO_ELEMENT.items():
        if data.get(graph_key) is not None:
            out[column] = data[graph_key]
    for key in ELEMENT_FIELDS:
        if key in attrs and not (attrs[key] is None and key in ELEMENT_NOT_NULL):
            out[key] = attrs[key]
    return out


FIXTURE_NOT_NULL = {"fixture_type", "channel_mode", "location", "gel", "purpose"}


def _fixture_changes(data: dict) -> dict:
    attrs = data.get("attributes") or {}
    return {
        key: attrs[key]
        for key in FIXTURE_ATTRS
        if key in attrs and not (attrs[key] is None and key in FIXTURE_NOT_NULL)
    }


async def _fixtures_on_device(db: AsyncSession, job_id: UUID, device_id: UUID) -> list:
    return [f for f in await lighting_service.list_fixtures(db, job_id) if f.device_id == device_id]


def _rigging_point_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if data.get("name") is not None:
        out["name"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    for key in ("trim_height_cm", "weight_capacity_kg"):
        if key in attrs:
            out[key] = attrs[key] or None
    return out


POWER_ATTR_KEYS = ("rating_amps", "active", "outputs")


def _power_node_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if data.get("name") is not None:
        out["name"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    if data.get("kind") in ("source", "distro", "breakout", "extension"):
        out["kind"] = data["kind"]
    for key in ("rating_amps", "active", "outputs"):
        if key in attrs and not (attrs[key] is None and key != "rating_amps"):
            out[key] = attrs[key]
    return out


async def _update_power_node(db: AsyncSession, job_id: UUID, node_id: UUID, changes: dict) -> None:
    """Edit a power node through the legacy handler, so its rules and errors are the same."""
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    try:
        await rigging_router.update_node(
            job_id, node_id, rigging_schemas.PowerNodeUpdate(**changes), db
        )
    except HTTPException:
        await db.rollback()
        raise


def _universe_changes(data: dict) -> dict:
    out: dict = {}
    attrs = data.get("attributes") or {}
    if "name" in data and data["name"] is not None:
        out["name"] = data["name"]
    if "notes" in data:
        out["notes"] = data["notes"] or ""
    if attrs.get("number"):
        out["number"] = attrs["number"]
    if "source_port" in attrs:
        out["source_port"] = attrs["source_port"] or ""
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
    if "ports" in data and data["ports"] is not None:
        # a connector group is a port with a connector or a channel count; the generic
        # ports the graph adds on its own carry neither and are not legacy data
        out["ports"] = [
            {
                "direction": p.get("direction") or "in",
                "connector": p.get("connector") or "",
                "count": p.get("channels") or 0,
            }
            for p in data["ports"]
            if p.get("connector") or p.get("channels")
        ]
    return out


VIDEO_TABLES = {
    "video_input_lists": (VideoInputList, _video_list_changes),
    "video_inputs": (VideoInput, _video_input_changes),
    "video_outputs": (VideoOutput, _video_output_changes),
}


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
    elif table in VIDEO_TABLES:
        model, make = VIDEO_TABLES[table]
        row, changes = await _video_row(db, job_id, model, legacy_id), make(data)
        if row is None or not changes:
            return False
        for key, value in changes.items():
            setattr(row, key, value)
        await db.commit()
    elif table == "rigging_points":
        from app.domains.rigging import service as rigging_service

        point = await rigging_service.get_point(db, job_id, legacy_id)
        changes = _rigging_point_changes(data)
        if point is None or not changes:
            return False
        for key, value in changes.items():
            setattr(point, key, value)
        await db.commit()
    elif table == "power_nodes":
        changes = _power_node_changes(data)
        if not changes:
            return False
        await _update_power_node(db, job_id, legacy_id, changes)
    elif table == "dmx_universes":
        universe = await db.get(DmxUniverse, legacy_id)
        changes = _universe_changes(data)
        if universe is None or not changes:
            return False
        number = changes.get("number")
        if number is not None and number != universe.number:
            taken = await db.scalar(
                select(DmxUniverse.id).where(
                    DmxUniverse.job_id == job_id,
                    DmxUniverse.number == number,
                    DmxUniverse.id != universe.id,
                )
            )
            if taken is not None:
                await db.rollback()
                raise HTTPException(status.HTTP_409_CONFLICT, f"Universe {number} already exists")
        for key, value in changes.items():
            setattr(universe, key, value)
        await db.commit()
    elif table == "lighting_fixtures":
        row = await lighting_service.get_fixture(db, job_id, legacy_id)
        changes = _fixture_changes(data)
        if row is None or not changes:
            return False
        await lighting_service.update_fixture(db, job_id, row, changes)
    elif table == "stage_plot_elements":
        changes = _element_changes(data)
        if not changes:
            return False
        return await service.update_plot_element(db, job_id, legacy_id, changes) is not None
    elif table == "audio_devices":
        row, changes = await service.get_device(db, legacy_id), _audio_device_changes(data)
        fixture_changes = _fixture_changes(data)
        if row is None:
            return False
        persisted = False
        power_changes = _power_node_changes({"attributes": data.get("attributes") or {}})
        power_changes = {k: v for k, v in power_changes.items() if k in POWER_ATTR_KEYS}
        if power_changes:
            from app.domains.rigging.models import PowerNode

            power_id = await db.scalar(
                select(PowerNode.id).where(
                    PowerNode.device_id == legacy_id, PowerNode.job_id == job_id
                )
            )
            if power_id is not None:
                await _update_power_node(db, job_id, power_id, power_changes)
                persisted = True
        if fixture_changes:
            # a device node shows its last fixture, so that is the one edits go to
            fixtures = await _fixtures_on_device(db, job_id, legacy_id)
            if fixtures:
                await lighting_service.update_fixture(db, job_id, fixtures[-1], fixture_changes)
                persisted = True
        if changes:
            row = await service.update_device(db, row, changes)
            persisted = True
        if not persisted:
            return False
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
    elif table == "stage_plot_elements":
        return await service.delete_plot_element(db, job_id, legacy_id)
    elif table == "rigging_points":
        from app.domains.rigging import service as rigging_service

        point = await rigging_service.get_point(db, job_id, legacy_id)
        if point is None:
            return False
        await db.delete(point)
        await db.commit()
    elif table == "power_nodes":
        from app.domains.rigging import router as rigging_router
        from app.domains.rigging import service as rigging_service

        if await rigging_service.get_node(db, job_id, legacy_id) is None:
            return False
        await rigging_router.delete_node(job_id, legacy_id, db)
    elif table in VIDEO_TABLES:
        row = await _video_row(db, job_id, VIDEO_TABLES[table][0], legacy_id)
        if row is None:
            return False
        await video_service.delete(db, row)
    elif table == "dmx_universes":
        universe = await db.get(DmxUniverse, legacy_id)
        if universe is None:
            return False
        await db.delete(universe)
        await db.commit()
    elif table == "lighting_fixtures":
        fixture = await lighting_service.get_fixture(db, job_id, legacy_id)
        if fixture is None:
            return False
        await lighting_service.delete_fixture(db, fixture)
    elif table == "audio_devices":
        row = await service.get_device(db, legacy_id)
        if row is None:
            return False
        if (
            row.patch_points
            or row.output_points
            or await _video_input_points(db, job_id, legacy_id)
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Move or delete the patch points on this device before removing it",
            )
        for fixture in await _fixtures_on_device(db, job_id, legacy_id):
            await lighting_service.delete_fixture(db, fixture)
        await service.delete_device(db, row)
        await publish_job_event(job_id, "device.delete", {"id": str(legacy_id)})
    else:
        return False
    return True


def _point_changes(attrs: dict) -> dict:
    return {key: attrs[key] for key in POINT_KEYS if key in attrs}


POWER_EDGE_TABLES = {
    "power_nodes",
    "power_node_feeds",
    "lighting_fixtures.power",
    "audio_devices.power",
}


async def _power_edge_to_legacy(
    db: AsyncSession, job_id: UUID, edge: ConnectionEdge, target: tuple[str, UUID], data: dict
) -> bool:
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    table, legacy_id = target
    attrs = data.get("attributes") or {}
    connector = attrs.get("connector")
    changes: dict = {}
    if connector is not None:
        changes["feed_connector"] = connector
    if "phase" in data:
        changes["phase"] = data["phase"]
    if not changes:
        return False
    try:
        if table == "power_nodes":
            await rigging_router.update_node(
                job_id, legacy_id, rigging_schemas.PowerNodeUpdate(**changes), db
            )
        elif table == "power_node_feeds":
            await _update_feed(db, job_id, legacy_id, changes)
        else:
            kind = "device" if table == "audio_devices.power" else "fixture"
            await _assign_fixture_load(db, job_id, legacy_id, changes, kind)
    except HTTPException:
        await db.rollback()
        raise
    return True


async def _update_feed(db: AsyncSession, job_id: UUID, feed_id: UUID, changes: dict) -> None:
    from app.domains.rigging import power_tree
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import service as rigging_service
    from app.domains.rigging.models import PowerNodeFeed

    feed = await db.get(PowerNodeFeed, feed_id)
    if feed is None or feed.job_id != job_id:
        return
    for key, value in changes.items():
        setattr(feed, key, value)
    nodes = await rigging_service.list_nodes(db, job_id)
    feeds = await rigging_service.list_feeds(db, job_id)
    rows = await rigging_service.collect_loads(db, job_id)
    evaluation = power_tree.evaluate(
        rigging_service.to_tree_nodes(nodes, feeds), rigging_service.to_tree_loads(rows)
    )
    names = [n.name for n in nodes if n.id in (feed.node_id, feed.parent_id)]
    await rigging_router._reject(rigging_router._problems(evaluation, *names))
    await db.commit()


async def _assign_fixture_load(
    db: AsyncSession, job_id: UUID, fixture_id: UUID, changes: dict, kind: str = "fixture"
) -> None:
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    assign = {"power_connector": changes["feed_connector"]} if "feed_connector" in changes else {}
    if assign:
        await rigging_router.assign_load(
            job_id, kind, fixture_id, rigging_schemas.LoadAssign(**assign), db
        )


async def _video_point(db: AsyncSession, job_id: UUID, table: str, point_id: UUID):
    if table == "video_patch_points":
        return await video_service.get_point(db, job_id, point_id)
    return await video_service.get_output_point(db, job_id, point_id)


async def edge_to_legacy(db: AsyncSession, job_id: UUID, edge: ConnectionEdge, data: dict) -> bool:
    """Write patch-point fields of an edge PATCH (connector, label, notes) to the legacy point."""
    target = legacy_target(edge)
    attrs = data.get("attributes") or {}
    if target is not None and target[0] in POWER_EDGE_TABLES:
        return await _power_edge_to_legacy(db, job_id, edge, target, data)
    if target is None or not attrs:
        return False
    table, legacy_id = target
    if table == "dmx_steps":
        step = await db.get(DmxStep, legacy_id)
        changes = {
            k: attrs[k] or "" for k in ("connector", "in_port", "out_port", "notes") if k in attrs
        }
        if step is None or not changes:
            return False
        for key, value in changes.items():
            setattr(step, key, value)
        await db.commit()
        return True
    if table == "dmx_universes":
        universe = await db.get(DmxUniverse, legacy_id)
        if universe is None or "source_port" not in attrs:
            return False
        universe.source_port = attrs["source_port"] or ""
        await db.commit()
        return True
    if table in ("video_patch_points", "video_output_patch_points"):
        point = await _video_point(db, job_id, table, legacy_id)
        changes = {k: attrs[k] or "" for k in VIDEO_POINT_KEYS if k in attrs}
        if point is None or not changes:
            return False
        for key, value in changes.items():
            setattr(point, key, value)
        await db.commit()
        return True
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
    ref = (edge.attributes or {}).get("legacy_ref") or ""
    if ref.startswith("stage_plot_elements.link:"):
        _, element_id, role = ref.split(":")
        return await _set_element_link(db, UUID(element_id), role, None)
    target = legacy_target(edge)
    if target is None:
        return False
    table, legacy_id = target
    if table == "dmx_steps":
        step = await db.get(DmxStep, legacy_id)
        if step is None:
            return False
        children = (await db.scalars(select(DmxStep).where(DmxStep.parent_id == step.id))).all()
        for child in children:
            child.parent_id = step.parent_id
        await db.flush()
        await db.delete(step)
        await db.commit()
        return True
    if table == "dmx_universes":
        universe = await db.get(DmxUniverse, legacy_id)
        if universe is None:
            return False
        universe.source_device_id = None
        universe.source_port = ""
        await db.commit()
        return True
    if table == "power_node_feeds":
        from app.domains.rigging.models import PowerNodeFeed

        feed = await db.get(PowerNodeFeed, legacy_id)
        if feed is None or feed.job_id != job_id:
            return False
        await db.delete(feed)
        await db.commit()
        return True
    if table == "power_nodes":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A node's own feed cannot be cut; move the node to another parent or delete it",
        )
    if table in ("lighting_fixtures.power", "audio_devices.power"):
        from app.domains.rigging import router as rigging_router
        from app.domains.rigging import schemas as rigging_schemas

        await rigging_router.assign_load(
            job_id,
            "device" if table == "audio_devices.power" else "fixture",
            legacy_id,
            rigging_schemas.LoadAssign(power_node_id=None),
            db,
        )
        return True
    if table == "video_patch_points":
        point = await _video_point(db, job_id, table, legacy_id)
        if point is None:
            return False
        await db.delete(point)
        await db.commit()
        return True
    if table == "video_output_patch_points":
        point = await _video_point(db, job_id, table, legacy_id)
        if point is None:
            return False
        children = (
            await db.scalars(
                select(VideoOutputPatchPoint).where(VideoOutputPatchPoint.parent_id == point.id)
            )
        ).all()
        for child in children:
            child.parent_id = point.parent_id
        await db.flush()
        await db.delete(point)
        await db.commit()
        return True
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


LINK_ROLES = {
    "channel": "audio_channel_patches",
    "device": "audio_devices",
    "video_input": "video_inputs",
    "lens": "audio_devices",
    "power_node": "power_nodes",
}


async def _set_element_link(
    db: AsyncSession, element_id: UUID, role: str, value: UUID | None
) -> bool:
    column = next((c for c, r in ELEMENT_LINKS.items() if r == role), None)
    element = await db.get(StagePlotElement, element_id)
    if column is None or element is None:
        return False
    setattr(element, column, value)
    await db.commit()
    return True


async def link_edge_to_legacy(
    db: AsyncSession, src: GraphDevice, dst: GraphDevice, role: str
) -> dict:
    """Validate a new ``link`` edge and write the element's legacy link column.

    Returns the edge attributes that tie the edge to its legacy twin.
    """
    source = legacy_target(src)
    target = legacy_target(dst)
    if src.kind != "plot_element" or source is None or source[0] != "stage_plot_elements":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A link starts at a plot element"
        )
    if role not in LINK_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Link role must be one of {sorted(LINK_ROLES)}"
        )
    if target is None or target[0] != LINK_ROLES[role]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A {role} link must point at a {LINK_ROLES[role]} node",
        )
    await _set_element_link(db, source[1], role, target[1])
    return {
        "legacy_ref": f"stage_plot_elements.link:{source[1]}:{role}",
        "role": role,
        "legacy_target": str(target[1]),
    }


async def create_element_twin(db: AsyncSession, job_id: UUID, data: dict) -> UUID:
    """Create the legacy plot element for a plot_element node made through the graph API."""
    attrs = data.get("attributes") or {}
    fields = {key: attrs[key] for key in ELEMENT_FIELDS if attrs.get(key) is not None}
    fields.setdefault("element_type", "custom")
    fields["label"] = attrs["label"] if "label" in attrs else data.get("name") or ""
    fields["position_x"] = data.get("canvas_x_cm") or 0.0
    fields["position_y"] = data.get("canvas_y_cm") or 0.0
    fields["rotation"] = data.get("canvas_rotation") or 0.0
    element = await service.create_plot_element(db, job_id, fields)
    return element.id


KNOWN_DEVICE_TYPES = {
    "digital_stagebox",
    "analog_stagebox",
    "mixer",
    "split",
    "network",
    "direct",
    "switcher",
    "router",
    "multiviewer",
    "camera",
    "lens",
    "ptz_camera",
    "computer",
    "patchbay",
    "converter",
    "encoder",
    "recorder",
    "screen",
    "projector",
    "fixture",
    "other",
}
DERIVED_DEVICE_FIELDS = (
    "name",
    "notes",
    "position",
    "kind",
    "domain",
    "attributes",
    "ports",
    "stockwire_product_id",
    "stockwire_product_name",
)


def device_needs_protection(device: GraphDevice, data: dict) -> bool:
    """Does this PATCH change something sync would otherwise overwrite from the legacy row?

    Fields the mirror writes back to the legacy row never need protecting, and neither do canvas
    fields (sync does not set them). Rows without a legacy twin are never synced.
    """
    target = legacy_target(device)
    if target is None:
        return False
    table = target[0]
    if table not in OWNED_ATTRS:
        return any(key in data for key in DERIVED_DEVICE_FIELDS)
    if "ports" in data and table != "audio_devices":
        return True
    attrs = data.get("attributes")
    if attrs is None:
        return False
    owned = OWNED_ATTRS[table]
    old = device.attributes or {}
    merged = {**old, **attrs}
    return any(merged.get(k) != old.get(k) for k in merged if k not in owned)


def edge_needs_protection(edge: ConnectionEdge, data: dict) -> bool:
    ref = (edge.attributes or {}).get("legacy_ref")
    if "phase" in data and (ref or "").partition(":")[0] not in ("power_nodes", "power_node_feeds"):
        return True
    if not ref or ref.partition(":")[0] in MIRRORED_EDGE_TABLES:
        return False
    return "attributes" in data


def merged_attributes(row: GraphDevice | ConnectionEdge, data: dict) -> dict:
    """PATCH keeps the keys it does not mention (legacy_ref, chain, list_id, ...)."""
    if data.get("attributes") is None:
        return data
    return {**data, "attributes": {**(row.attributes or {}), **data["attributes"]}}
