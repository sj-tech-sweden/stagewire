"""Clone a venue's Standard Base Rig onto a job.

A venue's base rig is the set of device/patch rows that belong to the venue
(``venue_id`` is set instead of ``job_id``). When a venue is assigned to a job
we deep-copy that whole graph into the job, reassigning ownership and remapping
every internal foreign key through an old-id -> new-id map. References to
entities that are not part of the cloned graph (e.g. Stockwire product ids,
venue power outlets) are left untouched because their ids are not in the map.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Uuid, select
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
from app.domains.lighting.models import (
    DmxStep,
    DmxUniverse,
    FixtureMode,
    FixtureType,
    LightingFixture,
)
from app.domains.rigging.models import PowerNode, PowerNodeFeed, RiggingPoint
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
    VideoPatchPoint,
)

# Root models are owned directly by a job or venue via ``job_id``/``venue_id``.
ROOT_MODELS = [
    ChannelList,
    AudioDevice,
    StagePlotElement,
    VideoInputList,
    LightingFixture,
    FixtureType,
    DmxUniverse,
    RiggingPoint,
    PowerNode,
    PowerNodeFeed,
]

# Child models are reached through a parent FK. Ordered so a parent is always
# cloned before its children.
CHILD_SPECS = [
    (AudioChannelPatch, "channel_list_id", ChannelList),
    (ChannelListOutput, "channel_list_id", ChannelList),
    (ChannelPatchPoint, "channel_id", AudioChannelPatch),
    (OutputPatchPoint, "output_id", ChannelListOutput),
    (VideoInput, "list_id", VideoInputList),
    (VideoOutput, "list_id", VideoInputList),
    (VideoPatchPoint, "input_id", VideoInput),
    (VideoOutputPatchPoint, "output_id", VideoOutput),
    (FixtureMode, "fixture_type_id", FixtureType),
    (DmxStep, "universe_id", DmxUniverse),
]


# Uuid columns that reference entities outside the cloned graph (e.g. an import
# batch or a venue power outlet). Their ids are never in the clone's id map, so
# remapping them would corrupt the data; always leave them untouched.
GLOBAL_REF_COLUMNS = {"import_batch_id", "venue_outlet_id"}


def _uuid_fk_columns(model) -> list[str]:
    return [
        col.name
        for col in model.__table__.columns
        if isinstance(col.type, Uuid)
        and not col.primary_key
        and col.name not in ("job_id", "venue_id")
        and col.name not in GLOBAL_REF_COLUMNS
    ]


async def _clone_model(
    db,
    model,
    id_map,
    cloned_rows,
    venue_id,
    job_id,
    parent_fk=None,
    parent_ids=None,
):
    if parent_fk is None:
        stmt = select(model).where(model.venue_id == venue_id)
    else:
        stmt = select(model).where(getattr(model, parent_fk).in_(parent_ids))
    rows = list((await db.execute(stmt)).scalars().all())
    cloned_old = set()
    for row in rows:
        data = {
            col.name: getattr(row, col.name)
            for col in model.__table__.columns
            if not col.primary_key
        }
        new = model(**data)
        new.id = uuid4()
        if "job_id" in data:
            new.job_id = job_id
        if "venue_id" in data:
            new.venue_id = None
        db.add(new)
        await db.flush()
        id_map[row.id] = new.id
        cloned_rows.append(new)
        cloned_old.add(row.id)
    return cloned_old


async def clone_base_rig_to_job(db: AsyncSession, venue_id: UUID, job_id: UUID) -> int:
    """Copy every venue-owned device/patch row into ``job_id``.

    Returns the number of rows cloned.
    """
    id_map: dict[UUID, UUID] = {}
    cloned_rows: list = []
    cloned_old_pks: dict = {}

    for model in ROOT_MODELS:
        cloned_old_pks[model] = await _clone_model(db, model, id_map, cloned_rows, venue_id, job_id)

    for child, parent_fk, parent in CHILD_SPECS:
        parent_ids = cloned_old_pks.get(parent)
        if not parent_ids:
            continue
        cloned_old_pks[child] = await _clone_model(
            db,
            child,
            id_map,
            cloned_rows,
            venue_id,
            job_id,
            parent_fk=parent_fk,
            parent_ids=parent_ids,
        )

    for new in cloned_rows:
        model = type(new)
        for col in _uuid_fk_columns(model):
            value = getattr(new, col)
            if value is not None and value in id_map:
                setattr(new, col, id_map[value])

    await db.flush()
    return len(cloned_rows)
