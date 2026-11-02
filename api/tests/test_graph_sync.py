import pytest
from audio_seed import seed_channel, seed_list, seed_point
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import AudioDevice, ProductionJob
from app.domains.graph.backfill import backfill_job
from app.main import app

BASE = "/api/v1"


async def _seed():
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Sync")
        db.add(job)
        await db.flush()
        box = AudioDevice(job_id=job.id, name="Stagebox", device_type="analog_stagebox")
        db.add(box)
        await db.commit()
        await backfill_job(db, job.id)  # the points refer to the device's graph node
        lst = await seed_list(db, job.id, name="FOH")
        ids = []
        for number, label in ((1, "Kick"), (2, "Snare")):
            ch = await seed_channel(db, lst, channel_number=number, source_label=label)
            await seed_point(db, ch, position=0, device_id=box.id)
            ids.append(ch.id)
        await db.commit()
        await backfill_job(db, job.id)
        return job.id, ids


async def _sync(client, headers, job_id):
    res = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _graph(client, headers, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=headers)).json()


@pytest.mark.asyncio
async def test_a_second_sync_changes_nothing_and_channels_edit_through_the_api(auth_headers):
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

        # the imported channel keeps its row id; an edit is one write to its node
        channel = (
            await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=auth_headers)
        ).json()[0]["channels"][0]
        assert channel["id"] == str(kick)
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{kick}",
            json={
                "source_label": "Kick In",
                "notes": "moved",
                "expected_revision": channel["revision"],
            },
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        devices = (await _graph(client, auth_headers, job_id))["devices"]
        node = next(d for d in devices if d["name"] == "Kick In")
        assert node["notes"] == "moved" and node["graph_edited"] is False


@pytest.mark.asyncio
async def test_a_sync_keeps_what_only_the_graph_knows(auth_headers):
    job_id, (kick, _) = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _sync(client, auth_headers, job_id)
        node = next(
            d
            for d in (await _graph(client, auth_headers, job_id))["devices"]
            if d["name"] == "Kick"
        )
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/graph/devices/{node['id']}",
            json={"canvas_x_cm": 120, "expected_revision": node["revision"]},
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        await _sync(client, auth_headers, job_id)
        node = next(
            d
            for d in (await _graph(client, auth_headers, job_id))["devices"]
            if d["name"] == "Kick"
        )
        assert node["canvas_x_cm"] == 120


@pytest.mark.asyncio
async def test_deleting_a_channel_removes_its_node_and_its_edges(auth_headers):
    job_id, (_, snare) = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _sync(client, auth_headers, job_id)
        assert len((await _graph(client, auth_headers, job_id))["edges"]) == 2
        channel = (
            await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=auth_headers)
        ).json()[0]["channels"][1]
        res = await client.delete(
            f"{BASE}/jobs/{job_id}/channels/{snare}",
            params={"expected_revision": channel["revision"]},
            headers=auth_headers,
        )
        assert res.status_code == 204, res.text
        after = await _graph(client, auth_headers, job_id)
        assert "Snare" not in {d["name"] for d in after["devices"]}
        assert len(after["edges"]) == 1
