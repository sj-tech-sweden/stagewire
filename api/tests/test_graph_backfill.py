import pytest
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelPatchPoint,
    ProductionJob,
)
from app.domains.lighting.models import DmxStep, DmxUniverse, LightingFixture
from app.domains.rigging.models import PowerNode
from app.main import app

BASE = "/api/v1"


async def _seed() -> str:
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Legacy")
        db.add(job)
        await db.flush()
        stagebox = AudioDevice(
            job_id=job.id,
            name="Stagebox",
            device_type="analog_stagebox",
            ports=[
                {"direction": "in", "connector": "XLR3", "count": 32},
                {"direction": "out", "connector": "XLR3", "count": 32},
            ],
            power_watts=120,
        )
        desk = AudioDevice(
            job_id=job.id,
            name="Desk",
            device_type="mixer",
            ports=[{"direction": "in", "connector": "XLR3", "count": 32}],
        )
        node = AudioDevice(job_id=job.id, name="Moving head", device_type="light")
        db.add_all([stagebox, desk, node])
        lst = ChannelList(job_id=job.id, name="FOH")
        db.add(lst)
        await db.flush()
        for number in (1, 2):
            channel = AudioChannelPatch(
                channel_list_id=lst.id, channel_number=number, source_label=f"Mic {number}"
            )
            db.add(channel)
            await db.flush()
            db.add_all(
                [
                    ChannelPatchPoint(channel_id=channel.id, position=0, device_id=stagebox.id),
                    ChannelPatchPoint(channel_id=channel.id, position=1, device_id=desk.id),
                ]
            )
        source = PowerNode(job_id=job.id, kind="source", name="Mains")
        db.add(source)
        await db.flush()
        distro = PowerNode(
            job_id=job.id, kind="distro", name="Distro", parent_id=source.id, phase="L1"
        )
        db.add(distro)
        await db.flush()
        fixture = LightingFixture(
            job_id=job.id,
            device_id=node.id,
            universe=1,
            dmx_address=1,
            fixture_type="Spot",
            power_node_id=distro.id,
        )
        db.add(fixture)
        uni = DmxUniverse(job_id=job.id, number=1, source_device_id=desk.id)
        db.add(uni)
        await db.flush()
        db.add(DmxStep(universe_id=uni.id, fixture_id=fixture.id))
        await db.commit()
        return str(job.id)


@pytest.mark.asyncio
async def test_backfill_maps_legacy_rows_and_is_idempotent(auth_headers):
    job_id = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        g = f"{BASE}/jobs/{job_id}/graph"
        first = await client.post(f"{g}/backfill", headers=auth_headers)
        assert first.status_code == 200, first.text
        # 3 devices + 1 channel list + 2 channels + 2 power nodes
        # 4 chain edges + 1 power feed + 1 dmx + 1 fixture power
        assert first.json()["devices"] == 8
        assert first.json()["edges"] == 7

        second = await client.post(f"{g}/backfill", headers=auth_headers)
        assert second.json()["devices"] == 0 and second.json()["edges"] == 0

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
        fixture = next(d for d in graph["devices"] if d["name"] == "Moving head")
        assert fixture["domain"] == "lighting" and fixture["attributes"]["dmx_address"] == 1

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
async def test_backfill_maps_output_chains_and_video(auth_headers):
    from app.domains.audio.models import ChannelListOutput, OutputPatchPoint
    from app.domains.video.models import (
        VideoInput,
        VideoInputList,
        VideoOutput,
        VideoOutputPatchPoint,
        VideoPatchPoint,
    )

    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Outputs")
        db.add(job)
        await db.flush()
        mk = lambda name, kind: AudioDevice(  # noqa: E731
            job_id=job.id, name=name, device_type=kind
        )
        console, amp, spk_a, spk_b = (
            mk("Console", "mixer"),
            mk("Amp", "amp"),
            mk("Spk A", "speaker"),
            mk("Spk B", "speaker"),
        )
        camera_rig, matrix, scaler, led = (
            mk("Cam rig", "other"),
            mk("Matrix", "switcher"),
            mk("Scaler", "other"),
            mk("LED proc", "other"),
        )
        db.add_all([console, amp, spk_a, spk_b, camera_rig, matrix, scaler, led])
        lst = ChannelList(job_id=job.id, name="FOH")
        db.add(lst)
        await db.flush()
        out = ChannelListOutput(channel_list_id=lst.id, name="Mon 1")
        db.add(out)
        await db.flush()
        p0 = OutputPatchPoint(output_id=out.id, position=0, device_id=console.id)
        db.add(p0)
        await db.flush()
        db.add_all(
            [
                OutputPatchPoint(output_id=out.id, position=1, device_id=amp.id),
                OutputPatchPoint(output_id=out.id, position=2, device_id=spk_a.id),
                OutputPatchPoint(output_id=out.id, position=3, device_id=spk_b.id, parent_id=p0.id),
            ]
        )
        vlist = VideoInputList(job_id=job.id, name="Video")
        db.add(vlist)
        await db.flush()
        vin = VideoInput(list_id=vlist.id, input_number=1, source_label="Cam 1")
        db.add(vin)
        await db.flush()
        db.add(VideoPatchPoint(input_id=vin.id, position=0, device_id=matrix.id, input_port="In 3"))
        vout = VideoOutput(list_id=vlist.id, output_number=1, destination_label="LED wall")
        db.add(vout)
        await db.flush()
        root = VideoOutputPatchPoint(output_id=vout.id, position=0, device_id=matrix.id)
        db.add(root)
        await db.flush()
        mid = VideoOutputPatchPoint(
            output_id=vout.id,
            position=1,
            device_id=scaler.id,
            parent_id=root.id,
            source_port="Out 1",
        )
        db.add(mid)
        await db.flush()
        db.add(
            VideoOutputPatchPoint(output_id=vout.id, position=2, device_id=led.id, parent_id=mid.id)
        )
        await db.commit()
        job_id = str(job.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        g = f"{BASE}/jobs/{job_id}/graph"
        first = await client.post(f"{g}/backfill", headers=auth_headers)
        assert first.status_code == 200, first.text
        # 8 devices + channel list + bus + video input + video destination
        assert first.json()["devices"] == 12
        # console->bus, bus->amp, amp->spkA, bus->spkB, cam->matrix,
        # matrix->scaler, scaler->led, led->dest
        assert first.json()["edges"] == 8
        assert (await client.post(f"{g}/backfill", headers=auth_headers)).json()["edges"] == 0

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

        cam = await client.get(
            f"{g}/devices/{by_name['Cam 1']['id']}/trace",
            params={"direction": "downstream"},
            headers=auth_headers,
        )
        assert by_name["LED wall"]["id"] in {h["device_id"] for h in cam.json()["hops"]}
        assert any(p["id"] == "In 3" for p in by_name["Matrix"]["ports"])
        assert any(p["id"] == "Out 1" for p in by_name["Matrix"]["ports"])
        assert any(p["id"] == "Out 1" for p in by_name["Scaler"]["ports"]) is False
