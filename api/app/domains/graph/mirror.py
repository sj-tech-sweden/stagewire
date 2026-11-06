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
from app.domains.graph import (
    audio_native,
    devices_native,
    dmx_native,
    fixtures_native,
    plot_native,
    power_native,
    video_native,
)
from app.domains.graph.backfill import (
    FIXTURE_ATTRS,
    MIRRORED_EDGE_TABLES,
    backfill_job,
)
from app.domains.graph.ids import power_id_of, public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.lighting import service as lighting_service

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
    from app.domains.graph.video_readers import device_has_video_input_points

    return await device_has_video_input_points(db, job_id, device_id)


FIXTURE_NOT_NULL = {"fixture_type", "channel_mode", "location", "gel", "purpose"}


def _fixture_changes(data: dict) -> dict:
    attrs = data.get("attributes") or {}
    return {
        key: attrs[key]
        for key in FIXTURE_ATTRS
        if key in attrs and not (attrs[key] is None and key in FIXTURE_NOT_NULL)
    }


async def _fixtures_on_device(
    db: AsyncSession, job_id: UUID | None, device_id: UUID, venue_id: UUID | None = None
) -> list:
    return [
        f
        for f in await lighting_service.list_fixtures(db, job_id, venue_id)
        if f.device_id == device_id
    ]


async def device_to_legacy(db: AsyncSession, job_id: UUID, device: GraphDevice, data: dict) -> bool:
    """After a graph PATCH of a device node: tell the open workspaces (the node is the device).

    Returns False: there is no legacy row to write, so nothing needs a sync.
    """
    if not devices_native.is_device(device):
        return False
    from app.domains.audio.router import _device_read

    row = await devices_native.get_device(db, public_id(device), job_id)
    if row is not None:
        await publish_job_event(job_id, "device.upsert", await _device_read(db, row))
    return False


async def _publish_list(db: AsyncSession, job_id: UUID, list_id: UUID) -> None:
    lst = await service.get_channel_list(db, list_id)
    if lst is not None:
        await publish_job_event(
            job_id, "list.upsert", audio_schemas.ChannelListRead.model_validate(lst)
        )


async def _publish_owner(db: AsyncSession, job_id: UUID, owner: GraphDevice) -> None:
    """After a patch point changed: the legacy events for its channel or its output's list."""
    if owner.kind == audio_native.CHANNEL:
        channel = await service.get_channel(db, public_id(owner), job_id)
        if channel is not None:
            await publish_job_event(
                job_id,
                "channel.upsert",
                audio_schemas.AudioChannelPatchRead.model_validate(channel),
            )
    else:
        await _publish_list(db, job_id, UUID(owner.attributes["channel_list_id"]))


async def delete_device_twin(db: AsyncSession, job_id: UUID, device: GraphDevice) -> bool:
    """The rules for removing a device node (checked first, so the caller can abort).

    A device with patch points cannot be removed (409); a fixture on it goes with it.
    """
    if not devices_native.is_device(device):
        return False
    device_id = public_id(device)
    if await audio_native.node_has_points(db, job_id, device.id) or (
        await _video_input_points(db, job_id, device_id)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Move or delete the patch points on this device before removing it",
        )
    for fixture in await _fixtures_on_device(db, job_id, device_id):
        await lighting_service.delete_fixture(db, fixture)
    await publish_job_event(job_id, "device.delete", {"id": str(device_id)})
    return True


def _point_changes(attrs: dict) -> dict:
    return {key: attrs[key] for key in POINT_KEYS if key in attrs}


POWER_EDGE_TABLES = {
    "device.power",
}


async def _power_edge_to_legacy(
    db: AsyncSession, job_id: UUID, edge: ConnectionEdge, target: tuple[str, UUID], data: dict
) -> bool:

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
        kind = "device" if table == "device.power" else "fixture"
        await _assign_fixture_load(db, job_id, legacy_id, changes, kind)
    except HTTPException:
        await db.rollback()
        raise
    return True


async def _assign_fixture_load(
    db: AsyncSession, job_id: UUID, fixture_id: UUID, changes: dict, kind: str = "fixture"
) -> None:
    from app.domains.rigging import router as rigging_router
    from app.domains.rigging import schemas as rigging_schemas

    assign = {"power_connector": changes["feed_connector"]} if "feed_connector" in changes else {}
    if assign:
        await rigging_router.assign_load(
            job_id=job_id,
            kind=kind,
            load_id=fixture_id,
            payload=rigging_schemas.LoadAssign(**assign),
            db=db,
            venue_id=None,
        )


async def edge_to_legacy(db: AsyncSession, job_id: UUID, edge: ConnectionEdge, data: dict) -> bool:
    """Write patch-point fields of an edge PATCH (connector, label, notes) to the legacy point."""
    if await video_native.point_from_edge(db, edge, data):
        return False
    if await dmx_native.step_from_edge(db, edge, data):
        return False
    if await power_native.edge_patch(db, job_id, edge, data):
        return False
    if await fixtures_native.edge_patch(db, job_id, edge, data):
        return False
    owner = await audio_native.edge_patch(db, edge, data)
    if owner is not None:  # a patch point of a channel or output: the sync redraws its edges
        await _publish_owner(db, job_id, owner)
        return True
    target = legacy_target(edge)
    attrs = data.get("attributes") or {}
    if target is not None and target[0] in POWER_EDGE_TABLES:
        return await _power_edge_to_legacy(db, job_id, edge, target, data)
    if target is None or not attrs:
        return False
    table, legacy_id = target
    return False


async def delete_edge_twin(db: AsyncSession, job_id: UUID, edge: ConnectionEdge) -> bool:
    if await video_native.delete_edge_point(db, edge):
        return False
    if await dmx_native.delete_step_edge(db, edge):
        return False
    if await power_native.edge_delete(db, job_id, edge):
        return False
    if await fixtures_native.edge_delete(db, job_id, edge):
        return False
    owner = await audio_native.edge_delete(db, edge)
    if owner is not None:
        await _publish_owner(db, job_id, owner)
        return True
    ref = (edge.attributes or {}).get("legacy_ref") or ""
    if ref.startswith("stage_plot_elements.link:"):
        _, element_id, role = ref.split(":")
        return await _clear_element_link(db, job_id, UUID(element_id), role)
    target = legacy_target(edge)
    if target is None:
        return False
    table, legacy_id = target
    if table == "device.power":
        from app.domains.rigging import router as rigging_router
        from app.domains.rigging import schemas as rigging_schemas

        await rigging_router.assign_load(
            job_id=job_id,
            kind="device" if table == "device.power" else "fixture",
            load_id=legacy_id,
            payload=rigging_schemas.LoadAssign(power_node_id=None),
            db=db,
            venue_id=None,
        )
        return True
    return False


LINK_ROLES = {
    "channel": "audio_channel_patches",
    "device": "device",
    "video_input": "video_inputs",
    "lens": "device",
    "power_node": "power_nodes",
}


async def _set_element_link(
    db: AsyncSession, job_id: UUID, element_id: UUID, role: str, value: UUID | None
) -> bool:
    """Write one link of a plot element (its attribute; the sync draws the edge).

    The six id links hold the target's public id; a power node link holds the graph node id of the
    power host and a rigging point the node id of the point (see ``plot_native``).
    """
    node = await plot_native.host_of(db, job_id, element_id)
    column = plot_native.ROLE_COLUMN.get(role, "power_node_id" if role == "power_node" else None)
    if node is None or column is None:
        return False
    attributes = dict(node.attributes or {})
    if value is None:
        attributes.pop(column, None)
        if role == "power_node":
            attributes["power_connector"] = ""
    elif role == "power_node":
        host = await power_native.host_of(db, job_id, value)
        if host is None:
            return False
        attributes[column] = str(host.id)
    else:
        attributes[column] = str(value)
    node.attributes = attributes
    await db.commit()
    return True


async def _clear_element_link(db: AsyncSession, job_id: UUID, element_id: UUID, role: str) -> bool:
    return await _set_element_link(db, job_id, element_id, role, None)


async def link_edge_to_legacy(
    db: AsyncSession, src: GraphDevice, dst: GraphDevice, role: str
) -> dict:
    """Validate a new ``link`` edge and write the element's link attribute.

    Returns the edge attributes that tie the edge to its element link (the sync keeps them).
    """
    target = legacy_target(dst)
    if not plot_native.is_element(src):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A link starts at a plot element"
        )
    if role not in LINK_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Link role must be one of {sorted(LINK_ROLES)}"
        )
    if role == "power_node" and power_id_of(dst) is not None:
        # power nodes are graph nodes; the link holds the power node's public id
        target = ("power_nodes", power_id_of(dst))
    if role == "video_input" and dst.kind == "video_input":
        # video inputs have no legacy row; the link holds the node's public id
        target = ("video_inputs", public_id(dst))
    if target is None or target[0] != LINK_ROLES[role]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A {role} link must point at a {LINK_ROLES[role]} node",
        )
    await _set_element_link(db, src.job_id, public_id(src), role, target[1])
    return {
        "legacy_ref": f"stage_plot_elements.link:{public_id(src)}:{role}",
        "role": role,
        "legacy_target": str(target[1]),
    }


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


def edge_needs_protection(edge: ConnectionEdge, data: dict) -> bool:
    ref = (edge.attributes or {}).get("legacy_ref")
    if "power_feed" in (edge.attributes or {}):
        return False  # a power feed: the power store owns it
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
