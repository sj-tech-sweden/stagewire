import pytest
from audio_seed import seed_channel, seed_device, seed_list, seed_output, seed_point
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.backfill import backfill_job
from app.main import app

BASE = "/api/v1"


async def _seed() -> str:
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Legacy")
        db.add(job)
        await db.flush()
        stagebox = await seed_device(
            db,
            job.id,
            name="Stagebox",
            device_type="analog_stagebox",
            ports=[
                {"direction": "in", "connector": "XLR3", "count": 32},
                {"direction": "out", "connector": "XLR3", "count": 32},
            ],
            power_watts=120,
        )
        desk = await seed_device(
            db,
            job.id,
            name="Desk",
            device_type="mixer",
            ports=[{"direction": "in", "connector": "XLR3", "count": 32}],
        )
        await seed_device(db, job.id, name="Moving head", device_type="light")
        await db.commit()
        lst = await seed_list(db, job.id, name="FOH")
        for number in (1, 2):
            channel = await seed_channel(
                db, lst, channel_number=number, source_label=f"Mic {number}"
            )
            await seed_point(db, channel, position=0, device_id=stagebox.id)
            await seed_point(db, channel, position=1, device_id=desk.id)
        await db.commit()
        await backfill_job(db, job.id)  # draws the patch edges from the points
        return str(job.id)


@pytest.mark.asyncio
async def test_backfill_maps_legacy_rows_and_is_idempotent(auth_headers):
    job_id = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        g = f"{BASE}/jobs/{job_id}/graph"
        # the sync drew 3 device nodes and the 4 chain edges of the 2 channels; another is a no-op
        second = await client.post(f"{g}/backfill", headers=auth_headers)
        assert second.status_code == 200, second.text
        assert second.json()["devices"] == 0 and second.json()["edges"] == 0
        assert len((await client.get(g, headers=auth_headers)).json()["edges"]) == 4

        graph = (await client.get(g, headers=auth_headers)).json()
        stagebox = next(d for d in graph["devices"] if d["name"] == "Stagebox")
        assert stagebox["ports"][0] == {
            "id": "in-xlr3",
            "direction": "in",
            "signal": "audio",
            "connector": "xlr3",
            "channels": 32,
            "max_connections": None,
            "label": "",
        }
        assert stagebox["attributes"]["power_w"] == 120

        mic = next(d for d in graph["devices"] if d["name"] == "Mic 1")
        trace = await client.get(
            f"{g}/devices/{mic['id']}/trace",
            params={"direction": "downstream", "signal": "audio"},
            headers=auth_headers,
        )
        assert [h["depth"] for h in trace.json()["hops"]] == [1, 2]
        assert trace.json()["issues"] == []

        issues = (await client.get(f"{g}/validate", headers=auth_headers)).json()
        assert [i for i in issues if i["code"] == "port_in_use"] == []


@pytest.mark.asyncio
async def test_backfill_maps_output_chains(auth_headers):
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Outputs")
        db.add(job)
        await db.flush()
        console = await seed_device(db, job.id, name="Console", device_type="mixer")
        amp = await seed_device(db, job.id, name="Amp", device_type="amp")
        spk_a = await seed_device(db, job.id, name="Spk A", device_type="speaker")
        spk_b = await seed_device(db, job.id, name="Spk B", device_type="speaker")
        await db.commit()
        await backfill_job(db, job.id)
        lst = await seed_list(db, job.id, name="FOH")
        out = await seed_output(db, lst, name="Mon 1")
        p0 = await seed_point(db, out, position=0, device_id=console.id)
        await seed_point(db, out, position=1, device_id=amp.id)
        await seed_point(db, out, position=2, device_id=spk_a.id)
        await seed_point(db, out, position=3, device_id=spk_b.id, parent_id=p0.id)
        await db.commit()
        await backfill_job(db, job.id)
        job_id = str(job.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        g = f"{BASE}/jobs/{job_id}/graph"
        # console->bus, bus->amp, amp->spkA, bus->spkB; another sync changes nothing
        assert (await client.post(f"{g}/backfill", headers=auth_headers)).json()["edges"] == 0
        graph = (await client.get(g, headers=auth_headers)).json()
        assert len([e for e in graph["edges"] if e["signal"] == "audio"]) == 4

        graph = (await client.get(g, headers=auth_headers)).json()
        by_name = {d["name"]: d for d in graph["devices"]}
        down = await client.get(
            f"{g}/devices/{by_name['Console']['id']}/trace",
            params={"direction": "downstream"},
            headers=auth_headers,
        )
        reached = {h["device_id"]: h["depth"] for h in down.json()["hops"]}
        assert reached[by_name["Mon 1"]["id"]] == 1
        assert reached[by_name["Amp"]["id"]] == 2
        assert reached[by_name["Spk A"]["id"]] == 3
        assert reached[by_name["Spk B"]["id"]] == 2
