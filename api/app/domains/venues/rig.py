"""Venue Standard Base Rig API — mirrors the job graph API's nested routes.

A venue's Standard Base Rig is stored as device/patch rows that belong to the
venue (``venue_id`` set, ``job_id`` NULL). To let the frontend's existing graph
editors (StagePlotPage, patch-flow, DMX, rigging) be reused unchanged, every
route here mirrors the corresponding ``/jobs/{job_id}/...`` path but is scoped to
``/venues/{venue_id}/rig/...``. The handlers reuse the per-domain Pydantic
schemas and models directly; the only difference from the job API is ownership
(``venue_id`` instead of ``job_id``) and that child FK values are taken from the
path (matching the job API's nested URLs).

Only the authoring (CRUD + nested children) routes are mirrored here. Read-only
compute/report endpoints (coverage, specs, exports, patch-sheets, …) are added in
a follow-up once the editor is wired.
"""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.domains.audio import schemas as audio_schemas
from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelListOutput,
    ChannelPatchPoint,
    OutputPatchPoint,
    StagePlotElement,
)
from app.domains.lighting import schemas as lighting_schemas
from app.domains.lighting.models import (
    DmxUniverse,
    FixtureMode,
    FixtureType,
    LightingFixture,
)
from app.domains.rigging import schemas as rigging_schemas
from app.domains.rigging.models import PowerNode, PowerNodeFeed, RiggingPoint
from app.domains.venues.models import Venue
from app.domains.video import schemas as video_schemas
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
    VideoPatchPoint,
)

router = APIRouter(prefix="/venues/{venue_id}/rig", tags=["venue-base-rig"])


def _path_params(path: str) -> list[str]:
    return re.findall(r"{([^}]+)}", path)


async def _require_venue(db: AsyncSession, venue_id: UUID) -> Venue:
    venue = await db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")
    return venue


async def _get_owned(db: AsyncSession, model, venue_id: UUID, row_id: UUID):
    row = await db.get(model, row_id)
    if row is None or row.venue_id != venue_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return row


def _eager_options(model, depth: int = 2):
    """Build selectinload options for the model's relationship graph.

    Eager-loading avoids implicit async lazy loads during response serialization
    (which can raise MissingGreenlet off the request path) and prevents N+1
    queries. selectinload issues a separate SELECT per collection, so multiple
    one-to-many collections on one parent are safe.
    """

    paths: list[list] = []

    def _walk(m, d, seen, prefix):
        if d == 0:
            return
        for rel in sa_inspect(m).relationships:
            path = prefix + [rel]
            paths.append(path)
            target = rel.mapper.class_
            if target not in seen:
                _walk(target, d - 1, seen | {m}, path)

    _walk(model, depth, set(), [])
    opts = []
    for path in paths:
        opt = selectinload(path[0])
        for rel in path[1:]:
            opt = opt.selectinload(rel)
        opts.append(opt)
    return opts


def _list_factory(model, read_schema):
    async def handler(venue_id: UUID, db: AsyncSession = Depends(get_db)):
        await _require_venue(db, venue_id)
        rows = (
            (
                await db.execute(
                    select(model)
                    .where(model.venue_id == venue_id)
                    .order_by(model.id)
                    .options(*_eager_options(model))
                )
            )
            .scalars()
            .all()
        )
        return [read_schema.model_validate(r) for r in rows]

    return handler


def _build_create(model, create_schema, parent_params, set_fields):
    if not parent_params:

        async def handler(
            venue_id: UUID, payload: create_schema, db: AsyncSession = Depends(get_db)
        ):
            await _require_venue(db, venue_id)
            data = payload.model_dump()
            data.pop("job_id", None)
            data.pop("venue_id", None)
            row = model(venue_id=venue_id, **data)
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row

        return handler

    pnames = ", ".join(parent_params)
    assigns = "\n".join(f"    data['{field}'] = {p}" for p, field in set_fields.items())
    src = (
        f"async def handler(venue_id: UUID, {pnames}: UUID, payload: {create_schema.__name__}, "
        "db: AsyncSession = Depends(get_db)):\n"
        "    await _require_venue(db, venue_id)\n"
        "    data = payload.model_dump()\n"
        "    data.pop('job_id', None)\n"
        "    data.pop('venue_id', None)\n" + assigns + "\n"
        "    row = model(venue_id=venue_id, **data)\n"
        "    db.add(row)\n"
        "    await db.commit()\n"
        "    await db.refresh(row)\n"
        "    return row\n"
    )
    ns = {
        "UUID": UUID,
        "Depends": Depends,
        "AsyncSession": AsyncSession,
        "get_db": get_db,
        "_require_venue": _require_venue,
        "model": model,
        create_schema.__name__: create_schema,
    }
    exec(compile(src, f"<rig create {model.__name__}>", "exec"), ns)
    return ns["handler"]


def _build_get(model, parent_params):
    if not parent_params:

        async def handler(venue_id: UUID, row_id: UUID, db: AsyncSession = Depends(get_db)):
            return await _get_owned(db, model, venue_id, row_id)

        return handler

    pnames = ", ".join(parent_params + ["row_id"])
    src = (
        f"async def handler(venue_id: UUID, {pnames}: UUID, "
        "db: AsyncSession = Depends(get_db)):\n"
        "    return await _get_owned(db, model, venue_id, row_id)\n"
    )
    ns = {
        "UUID": UUID,
        "Depends": Depends,
        "AsyncSession": AsyncSession,
        "get_db": get_db,
        "_get_owned": _get_owned,
        "model": model,
    }
    exec(compile(src, f"<rig get {model.__name__}>", "exec"), ns)
    return ns["handler"]


def _build_update(model, update_schema, parent_params):
    if not parent_params:

        async def handler(
            venue_id: UUID,
            row_id: UUID,
            payload: update_schema,
            db: AsyncSession = Depends(get_db),
        ):
            row = await _get_owned(db, model, venue_id, row_id)
            for key, value in payload.model_dump(exclude_unset=True).items():
                setattr(row, key, value)
            await db.commit()
            await db.refresh(row)
            return row

        return handler

    pnames = ", ".join(parent_params + ["row_id"])
    src = (
        f"async def handler(venue_id: UUID, {pnames}: UUID, payload: {update_schema.__name__}, "
        "db: AsyncSession = Depends(get_db)):\n"
        "    row = await _get_owned(db, model, venue_id, row_id)\n"
        "    for key, value in payload.model_dump(exclude_unset=True).items():\n"
        "        setattr(row, key, value)\n"
        "    await db.commit()\n"
        "    await db.refresh(row)\n"
        "    return row\n"
    )
    ns = {
        "UUID": UUID,
        "Depends": Depends,
        "AsyncSession": AsyncSession,
        "get_db": get_db,
        "_get_owned": _get_owned,
        "model": model,
        update_schema.__name__: update_schema,
    }
    exec(compile(src, f"<rig update {model.__name__}>", "exec"), ns)
    return ns["handler"]


def _build_delete(model, parent_params):
    if not parent_params:

        async def handler(venue_id: UUID, row_id: UUID, db: AsyncSession = Depends(get_db)):
            row = await _get_owned(db, model, venue_id, row_id)
            await db.delete(row)
            await db.commit()
            return None

        return handler

    pnames = ", ".join(parent_params + ["row_id"])
    src = (
        f"async def handler(venue_id: UUID, {pnames}: UUID, "
        "db: AsyncSession = Depends(get_db)):\n"
        "    row = await _get_owned(db, model, venue_id, row_id)\n"
        "    await db.delete(row)\n"
        "    await db.commit()\n"
        "    return None\n"
    )
    ns = {
        "UUID": UUID,
        "Depends": Depends,
        "AsyncSession": AsyncSession,
        "get_db": get_db,
        "_get_owned": _get_owned,
        "model": model,
    }
    exec(compile(src, f"<rig delete {model.__name__}>", "exec"), ns)
    return ns["handler"]


def _register(
    create_path,
    get_path,
    model,
    create_schema,
    update_schema,
    read_schema,
    list_path=None,
    set_fields=None,
):
    """Register CRUD routes mirroring the job API's nested path layout.

    ``set_fields`` maps a path parameter name to the model attribute it should be
    written to on create (e.g. ``{"parent_id": "channel_list_id"}``). Path params
    not present in ``set_fields`` are still declared (FastAPI requires it) but are
    not written to the row.
    """
    set_fields = set_fields or {}
    create_params = _path_params(create_path)
    get_params = [p for p in _path_params(get_path) if p != "row_id"]

    if list_path:
        router.add_api_route(
            list_path,
            _list_factory(model, read_schema),
            methods=["GET"],
            response_model=list[read_schema],
        )
    router.add_api_route(
        create_path,
        _build_create(model, create_schema, create_params, set_fields),
        methods=["POST"],
        response_model=read_schema,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        get_path,
        _build_get(model, get_params),
        methods=["GET"],
        response_model=read_schema,
    )
    router.add_api_route(
        get_path,
        _build_update(model, update_schema, get_params),
        methods=["PATCH"],
        response_model=read_schema,
    )
    router.add_api_route(
        get_path,
        _build_delete(model, get_params),
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
    )


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
_register(
    "/channel-lists",
    "/channel-lists/{row_id}",
    ChannelList,
    audio_schemas.ChannelListCreate,
    audio_schemas.ChannelListUpdate,
    audio_schemas.ChannelListRead,
    list_path="/channel-lists",
)
_register(
    "/channel-lists/{parent_id}/channels",
    "/channels/{row_id}",
    AudioChannelPatch,
    audio_schemas.AudioChannelPatchCreate,
    audio_schemas.AudioChannelPatchUpdate,
    audio_schemas.AudioChannelPatchRead,
    set_fields={"parent_id": "channel_list_id"},
)
_register(
    "/channels/{parent_id}/patch-points",
    "/channels/{parent_id}/patch-points/{row_id}",
    ChannelPatchPoint,
    audio_schemas.ChannelPatchPointCreate,
    audio_schemas.ChannelPatchPointUpdate,
    audio_schemas.ChannelPatchPointRead,
    set_fields={"parent_id": "channel_id"},
)
_register(
    "/channel-lists/{parent_id}/outputs",
    "/channel-lists/{parent_id}/outputs/{row_id}",
    ChannelListOutput,
    audio_schemas.ChannelListOutputCreate,
    audio_schemas.ChannelListOutputUpdate,
    audio_schemas.ChannelListOutputRead,
    set_fields={"parent_id": "channel_list_id"},
)
_register(
    "/channel-lists/{parent_id}/outputs/{output_id}/points",
    "/channel-lists/{parent_id}/outputs/{output_id}/points/{row_id}",
    OutputPatchPoint,
    audio_schemas.OutputPatchPointCreate,
    audio_schemas.OutputPatchPointUpdate,
    audio_schemas.OutputPatchPointRead,
    set_fields={"output_id": "output_id"},
)
_register(
    "/devices",
    "/devices/{row_id}",
    AudioDevice,
    audio_schemas.AudioDeviceCreate,
    audio_schemas.AudioDeviceUpdate,
    audio_schemas.AudioDeviceRead,
    list_path="/devices",
)
_register(
    "/plot-elements",
    "/plot-elements/{row_id}",
    StagePlotElement,
    audio_schemas.StagePlotElementCreate,
    audio_schemas.StagePlotElementUpdate,
    audio_schemas.StagePlotElementRead,
    list_path="/plot-elements",
)

# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------
_register(
    "/video-lists",
    "/video-lists/{row_id}",
    VideoInputList,
    video_schemas.VideoInputListCreate,
    video_schemas.VideoInputListUpdate,
    video_schemas.VideoInputListRead,
    list_path="/video-lists",
)
_register(
    "/video-lists/{parent_id}/inputs",
    "/video-inputs/{row_id}",
    VideoInput,
    video_schemas.VideoInputCreate,
    video_schemas.VideoInputUpdate,
    video_schemas.VideoInputRead,
    set_fields={"parent_id": "list_id"},
)
_register(
    "/video-inputs/{parent_id}/patch-points",
    "/video-inputs/{parent_id}/patch-points/{row_id}",
    VideoPatchPoint,
    video_schemas.VideoPatchPointCreate,
    video_schemas.VideoPatchPointUpdate,
    video_schemas.VideoPatchPointRead,
    set_fields={"parent_id": "input_id"},
)
_register(
    "/video-lists/{parent_id}/outputs",
    "/video-outputs/{row_id}",
    VideoOutput,
    video_schemas.VideoOutputCreate,
    video_schemas.VideoOutputUpdate,
    video_schemas.VideoOutputRead,
    set_fields={"parent_id": "list_id"},
)
_register(
    "/video-outputs/{parent_id}/patch-points",
    "/video-outputs/{parent_id}/patch-points/{row_id}",
    VideoOutputPatchPoint,
    video_schemas.VideoOutputPatchPointCreate,
    video_schemas.VideoOutputPatchPointUpdate,
    video_schemas.VideoOutputPatchPointRead,
    set_fields={"parent_id": "output_id"},
)

# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------
_register(
    "/fixtures",
    "/fixtures/{row_id}",
    LightingFixture,
    lighting_schemas.FixtureCreate,
    lighting_schemas.FixtureUpdate,
    lighting_schemas.FixtureRead,
    list_path="/fixtures",
)
_register(
    "/fixture-types",
    "/fixture-types/{row_id}",
    FixtureType,
    lighting_schemas.FixtureTypeCreate,
    lighting_schemas.FixtureTypeUpdate,
    lighting_schemas.FixtureTypeRead,
    list_path="/fixture-types",
)
_register(
    "/fixture-types/{parent_id}/modes",
    "/fixture-types/{parent_id}/modes/{row_id}",
    FixtureMode,
    lighting_schemas.FixtureModeCreate,
    lighting_schemas.FixtureModeUpdate,
    lighting_schemas.FixtureModeRead,
    set_fields={"parent_id": "fixture_type_id"},
)
_register(
    "/dmx-universes",
    "/dmx-universes/{row_id}",
    DmxUniverse,
    lighting_schemas.DmxUniverseCreate,
    lighting_schemas.DmxUniverseUpdate,
    lighting_schemas.DmxUniverseRead,
    list_path="/dmx-universes",
)

# ---------------------------------------------------------------------------
# Rigging
# ---------------------------------------------------------------------------
_register(
    "/rigging-points",
    "/rigging-points/{row_id}",
    RiggingPoint,
    rigging_schemas.RiggingPointCreate,
    rigging_schemas.RiggingPointUpdate,
    rigging_schemas.RiggingPointRead,
    list_path="/rigging-points",
)
_register(
    "/power-nodes",
    "/power-nodes/{row_id}",
    PowerNode,
    rigging_schemas.PowerNodeCreate,
    rigging_schemas.PowerNodeUpdate,
    rigging_schemas.PowerNodeRead,
    list_path="/power-nodes",
)
_register(
    "/power-nodes/{parent_id}/feeds",
    "/power-nodes/{parent_id}/feeds/{row_id}",
    PowerNodeFeed,
    rigging_schemas.PowerNodeFeedCreate,
    rigging_schemas.PowerNodeFeedUpdate,
    rigging_schemas.PowerNodeFeedRead,
    set_fields={"parent_id": "parent_id"},
)
