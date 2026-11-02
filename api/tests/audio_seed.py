"""Seed channel lists the way the app makes them (graph nodes), in the style of the old ORM rows.

The devices must have been synced to the graph first (``backfill_job``): a patch point refers to
its device's node.
"""

from app.domains.graph import audio_native as an


async def seed_list(db, job_id, **data):
    return await an.create_list(db, job_id, data)


async def seed_channel(db, lst, **data):
    return await an.create_channel(db, lst.id, data)


async def seed_output(db, lst, **data):
    return await an.create_output(db, lst.id, data)


async def seed_point(db, owner, **data):
    """A patch point on a channel (``channel_id`` in the row) or an output."""
    kind = an.CHANNEL if hasattr(owner, "source_label") else an.OUTPUT
    return await an.create_point(db, kind, owner.id, data)


async def seed_device(db, job_id, **data):
    """A device (a graph node); its ``.id`` is the id patch points and plot links use."""
    from app.domains.graph import devices_native

    return await devices_native.create_device(db, job_id, data)
