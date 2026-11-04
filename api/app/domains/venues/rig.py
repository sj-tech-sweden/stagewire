"""Owner-agnostic CRUD for a venue's Standard Base Rig.

A venue's base rig is stored as device/patch rows that belong to the venue
(``venue_id`` set, ``job_id`` NULL). This router exposes the same create/read/
update/delete operations the job graph uses, but scoped to a venue, so the
Venues "Base Rig" editor can reuse the normal graph tools against venue-owned
rows. It reuses the existing per-domain Pydantic schemas for validation and the
domain models directly.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    DmxStep,
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

# slug -> (model, Create schema, Update schema, Read schema)
RIG_REGISTRY: dict[str, tuple] = {
    "audio-devices": (
        AudioDevice,
        audio_schemas.AudioDeviceCreate,
        audio_schemas.AudioDeviceUpdate,
        audio_schemas.AudioDeviceRead,
    ),
    "audio-channel-lists": (
        ChannelList,
        audio_schemas.ChannelListCreate,
        audio_schemas.ChannelListUpdate,
        audio_schemas.ChannelListRead,
    ),
    "audio-channels": (
        AudioChannelPatch,
        audio_schemas.AudioChannelPatchCreate,
        audio_schemas.AudioChannelPatchUpdate,
        audio_schemas.AudioChannelPatchRead,
    ),
    "audio-channel-outputs": (
        ChannelListOutput,
        audio_schemas.ChannelListOutputCreate,
        audio_schemas.ChannelListOutputUpdate,
        audio_schemas.ChannelListOutputRead,
    ),
    "audio-channel-patch-points": (
        ChannelPatchPoint,
        audio_schemas.ChannelPatchPointCreate,
        audio_schemas.ChannelPatchPointUpdate,
        audio_schemas.ChannelPatchPointRead,
    ),
    "audio-output-patch-points": (
        OutputPatchPoint,
        audio_schemas.OutputPatchPointCreate,
        audio_schemas.OutputPatchPointUpdate,
        audio_schemas.OutputPatchPointRead,
    ),
    "stage-plot-elements": (
        StagePlotElement,
        audio_schemas.StagePlotElementCreate,
        audio_schemas.StagePlotElementUpdate,
        audio_schemas.StagePlotElementRead,
    ),
    "video-input-lists": (
        VideoInputList,
        video_schemas.VideoInputListCreate,
        video_schemas.VideoInputListUpdate,
        video_schemas.VideoInputListRead,
    ),
    "video-inputs": (
        VideoInput,
        video_schemas.VideoInputCreate,
        video_schemas.VideoInputUpdate,
        video_schemas.VideoInputRead,
    ),
    "video-outputs": (
        VideoOutput,
        video_schemas.VideoOutputCreate,
        video_schemas.VideoOutputUpdate,
        video_schemas.VideoOutputRead,
    ),
    "video-patch-points": (
        VideoPatchPoint,
        video_schemas.VideoPatchPointCreate,
        video_schemas.VideoPatchPointUpdate,
        video_schemas.VideoPatchPointRead,
    ),
    "video-output-patch-points": (
        VideoOutputPatchPoint,
        video_schemas.VideoOutputPatchPointCreate,
        video_schemas.VideoOutputPatchPointUpdate,
        video_schemas.VideoOutputPatchPointRead,
    ),
    "lighting-fixtures": (
        LightingFixture,
        lighting_schemas.FixtureCreate,
        lighting_schemas.FixtureUpdate,
        lighting_schemas.FixtureRead,
    ),
    "fixture-types": (
        FixtureType,
        lighting_schemas.FixtureTypeCreate,
        lighting_schemas.FixtureTypeUpdate,
        lighting_schemas.FixtureTypeRead,
    ),
    "fixture-modes": (
        FixtureMode,
        lighting_schemas.FixtureModeCreate,
        lighting_schemas.FixtureModeUpdate,
        lighting_schemas.FixtureModeRead,
    ),
    "dmx-universes": (
        DmxUniverse,
        lighting_schemas.DmxUniverseCreate,
        lighting_schemas.DmxUniverseUpdate,
        lighting_schemas.DmxUniverseRead,
    ),
    "dmx-steps": (
        DmxStep,
        lighting_schemas.DmxStepCreate,
        lighting_schemas.DmxStepUpdate,
        lighting_schemas.DmxStepRead,
    ),
    "rigging-points": (
        RiggingPoint,
        rigging_schemas.RiggingPointCreate,
        rigging_schemas.RiggingPointUpdate,
        rigging_schemas.RiggingPointRead,
    ),
    "power-nodes": (
        PowerNode,
        rigging_schemas.PowerNodeCreate,
        rigging_schemas.PowerNodeUpdate,
        rigging_schemas.PowerNodeRead,
    ),
    "power-node-feeds": (
        PowerNodeFeed,
        rigging_schemas.PowerNodeFeedCreate,
        rigging_schemas.PowerNodeFeedUpdate,
        rigging_schemas.PowerNodeFeedRead,
    ),
}

# Child entities whose Create schema omits the parent FK (the job API supplies it
# via the path). The venue rig API accepts it in the POST body instead.
PARENT_FK: dict[str, str] = {
    "audio-channels": "channel_list_id",
    "audio-channel-outputs": "channel_list_id",
    "audio-channel-patch-points": "channel_id",
    "audio-output-patch-points": "output_id",
    "video-inputs": "list_id",
    "video-outputs": "list_id",
    "video-patch-points": "input_id",
    "video-output-patch-points": "output_id",
    "fixture-modes": "fixture_type_id",
    "dmx-steps": "universe_id",
}


def _rig_create_schema(key: str, create_schema):
    fk = PARENT_FK.get(key)
    if fk is None or fk in create_schema.model_fields:
        return create_schema
    extended = create_model(
        f"{create_schema.__name__}Rig",
        **{fk: (UUID, ...)},
        __base__=create_schema,
    )
    return extended


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


def _list_factory(model, read_schema):
    async def handler(venue_id: UUID, db: AsyncSession = Depends(get_db)):
        await _require_venue(db, venue_id)
        rows = (
            (await db.execute(select(model).where(model.venue_id == venue_id).order_by(model.id)))
            .scalars()
            .all()
        )
        return [read_schema.model_validate(r) for r in rows]

    return handler


def _create_factory(model, create_schema, read_schema):
    async def handler(venue_id: UUID, payload: create_schema, db: AsyncSession = Depends(get_db)):
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


def _get_factory(model, read_schema):
    async def handler(venue_id: UUID, row_id: UUID, db: AsyncSession = Depends(get_db)):
        return await _get_owned(db, model, venue_id, row_id)

    return handler


def _update_factory(model, update_schema):
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


def _delete_factory(model):
    async def handler(venue_id: UUID, row_id: UUID, db: AsyncSession = Depends(get_db)):
        row = await _get_owned(db, model, venue_id, row_id)
        await db.delete(row)
        await db.commit()
        return None

    return handler


for _key, (_model, _create, _update, _read) in RIG_REGISTRY.items():
    _create = _rig_create_schema(_key, _create)
    router.add_api_route(
        f"/{_key}",
        _list_factory(_model, _read),
        methods=["GET"],
        response_model=list[_read],
    )
    router.add_api_route(
        f"/{_key}",
        _create_factory(_model, _create, _read),
        methods=["POST"],
        response_model=_read,
        status_code=status.HTTP_201_CREATED,
    )
    router.add_api_route(
        f"/{_key}/{{row_id}}",
        _get_factory(_model, _read),
        methods=["GET"],
        response_model=_read,
    )
    router.add_api_route(
        f"/{_key}/{{row_id}}",
        _update_factory(_model, _update),
        methods=["PATCH"],
        response_model=_read,
    )
    router.add_api_route(
        f"/{_key}/{{row_id}}",
        _delete_factory(_model),
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
