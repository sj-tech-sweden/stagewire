import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import db as db_mod
from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelPatchPoint,
    ProductionJob,
)
from app.main import app

BASE = "/api/v1"


async def _seed():
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Sync")
        db.add(job)
        await db.flush()
        box = AudioDevice(job_id=job.id, name="Stagebox", device_type="analog_stagebox")
        db.add(box)
        lst = ChannelList(job_id=job.id, name="FOH")
        db.add(lst)
        await db.flush()
        ids = []
        for number, label in ((1, "Kick"), (2, "Snare")):
            ch = AudioChannelPatch(
                channel_list_id=lst.id, channel_number=number, source_label=label
            )
            db.add(ch)
            await db.flush()
            db.add(ChannelPatchPoint(channel_id=ch.id, position=0, device_id=box.id))
            ids.append(ch.id)
        await db.commit()
        return job.id, ids


async def _sync(client, headers, job_id):
    res = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _graph(client, headers, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=headers)).json()


@pytest.mark.asyncio
async def test_sync_refreshes_untouched_rows_and_is_a_no_op_when_nothing_changed(auth_headers):
    job_id, (kick, _) = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _sync(client, auth_headers, job_id)
        again = await _sync(client, auth_headers, job_id)
        assert (again["devices"], again["edges"], again["updated"], again["removed"]) == (
            0,
            0,
            0,
            0,
        )

        async with db_mod.SessionLocal() as db:
            row = await db.get(AudioChannelPatch, kick)
            row.source_label = "Kick In"
            row.notes = "moved"
            await db.commit()
        changed = await _sync(client, auth_headers, job_id)
        assert changed["updated"] == 1
        devices = (await _graph(client, auth_headers, job_id))["devices"]
        node = next(d for d in devices if d["name"] == "Kick In")
        assert node["notes"] == "moved"
        assert node["revision"] == 2 and node["graph_edited"] is False


@pytest.mark.asyncio
async def test_sync_never_overwrites_rows_edited_in_the_graph(auth_headers):
    job_id, (kick, _) = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _sync(client, auth_headers, job_id)
        devices = (await _graph(client, auth_headers, job_id))["devices"]
        node = next(d for d in devices if d["name"] == "Kick")
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/graph/devices/{node['id']}",
            json={"name": "Kick (graph)", "expected_revision": node["revision"]},
            headers=auth_headers,
        )
        assert res.json()["graph_edited"] is True

        async with db_mod.SessionLocal() as db:
            row = await db.get(AudioChannelPatch, kick)
            row.source_label = "Kick (legacy)"
            await db.commit()
        await _sync(client, auth_headers, job_id)
        names = {d["name"] for d in (await _graph(client, auth_headers, job_id))["devices"]}
        assert "Kick (graph)" in names and "Kick (legacy)" not in names


@pytest.mark.asyncio
async def test_sync_removes_rows_deleted_from_the_legacy_tables(auth_headers):
    job_id, (_, snare) = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _sync(client, auth_headers, job_id)
        before = await _graph(client, auth_headers, job_id)
        assert len(before["edges"]) == 2

        async with db_mod.SessionLocal() as db:
            await db.execute(delete(ChannelPatchPoint).where(ChannelPatchPoint.channel_id == snare))
            await db.execute(delete(AudioChannelPatch).where(AudioChannelPatch.id == snare))
            await db.commit()
        result = await _sync(client, auth_headers, job_id)
        assert result["removed"] == 2
        after = await _graph(client, auth_headers, job_id)
        assert "Snare" not in {d["name"] for d in after["devices"]}
        assert len(after["edges"]) == 1

        async with db_mod.SessionLocal() as db:
            left = await db.scalars(select(ChannelPatchPoint))
            assert len(left.all()) >= 1
