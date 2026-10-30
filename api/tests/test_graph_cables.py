import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import (
    AudioChannelPatch,
    AudioDevice,
    ChannelList,
    ChannelListOutput,
    ChannelPatchPoint,
    OutputPatchPoint,
    ProductionJob,
    StagePlotElement,
)
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.reports.cable_routing import (
    derive_cables,
    derive_cables_from_graph,
    routed_cable_paths,
    routed_cable_paths_from_graph,
)
from app.domains.video.models import (
    VideoInput,
    VideoInputList,
    VideoOutput,
    VideoOutputPatchPoint,
    VideoPatchPoint,
)
from app.main import app

BASE = "/api/v1"


def _element(job_id, kind, x, y, **links):
    return StagePlotElement(
        job_id=job_id,
        element_type=kind,
        position_x=x,
        position_y=y,
        width_cm=40,
        height_cm=40,
        **links,
    )


async def _seed():
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Cables")
        db.add(job)
        await db.flush()
        devices = {
            name: AudioDevice(job_id=job.id, name=name, device_type=kind)
            for name, kind in (
                ("Stagebox", "analog_stagebox"),
                ("Desk", "mixer"),
                ("Amp", "amp"),
                ("Matrix", "switcher"),
                ("Scaler", "other"),
                ("Camrig", "other"),
                ("Wedge", "monitor"),
            )
        }
        db.add_all(devices.values())
        lst = ChannelList(job_id=job.id, name="FOH")
        db.add(lst)
        await db.flush()
        channels = []
        for number in (1, 2):
            ch = AudioChannelPatch(
                channel_list_id=lst.id, channel_number=number, source_label=f"C{number}"
            )
            db.add(ch)
            await db.flush()
            for position, name in enumerate(("Stagebox", "Desk")):
                db.add(
                    ChannelPatchPoint(
                        channel_id=ch.id, position=position, device_id=devices[name].id
                    )
                )
            channels.append(ch)
        out = ChannelListOutput(channel_list_id=lst.id, name="Mon 1")
        db.add(out)
        await db.flush()
        p0 = OutputPatchPoint(output_id=out.id, position=0, device_id=devices["Desk"].id)
        db.add(p0)
        await db.flush()
        p1 = OutputPatchPoint(output_id=out.id, position=1, device_id=devices["Amp"].id)
        p2 = OutputPatchPoint(
            output_id=out.id, position=2, device_id=devices["Stagebox"].id, parent_id=p0.id
        )
        db.add_all([p1, p2])
        vlist = VideoInputList(job_id=job.id, name="Video")
        db.add(vlist)
        await db.flush()
        vin = VideoInput(list_id=vlist.id, input_number=1, source_label="Cam")
        db.add(vin)
        await db.flush()
        for position, name in enumerate(("Camrig", "Matrix", "Scaler")):
            db.add(VideoPatchPoint(input_id=vin.id, position=position, device_id=devices[name].id))
        vout = VideoOutput(list_id=vlist.id, output_number=1, destination_label="LED")
        db.add(vout)
        await db.flush()
        root = VideoOutputPatchPoint(output_id=vout.id, position=0, device_id=devices["Matrix"].id)
        db.add(root)
        await db.flush()
        db.add(
            VideoOutputPatchPoint(
                output_id=vout.id, position=1, device_id=devices["Scaler"].id, parent_id=root.id
            )
        )
        j = job.id
        db.add_all(
            [
                _element(j, "microphone", 100, 100, linked_channel_id=channels[0].id),
                _element(j, "performer", 200, 100, linked_channel_id=channels[1].id),
                _element(j, "stagebox", 300, 300, linked_device_id=devices["Stagebox"].id),
                _element(j, "mixer", 600, 300, linked_device_id=devices["Desk"].id),
                _element(j, "amp", 500, 500, linked_device_id=devices["Amp"].id),
                _element(
                    j,
                    "speaker",
                    700,
                    500,
                    linked_output_point_id=p1.id,
                    linked_device_id=devices["Wedge"].id,
                ),
                _element(j, "speaker", 800, 500, linked_device_id=devices["Amp"].id),
                _element(
                    j,
                    "camera",
                    50,
                    400,
                    linked_video_input_id=vin.id,
                    linked_device_id=devices["Camrig"].id,
                ),
                _element(j, "projector", 60, 420, linked_video_input_id=vin.id),
                _element(j, "switcher", 400, 50, linked_device_id=devices["Matrix"].id),
                _element(j, "other", 450, 80, linked_device_id=devices["Scaler"].id),
            ]
        )
        await db.commit()
        return job.id, p2.id


@pytest.mark.asyncio
async def test_graph_cables_match_legacy_cables_and_saved_routes(auth_headers):
    job_id, hidden_point_id = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=auth_headers)
        assert res.status_code == 200, res.text

    async with db_mod.SessionLocal() as db:
        lists = (await db.scalars(select(ChannelList).where(ChannelList.job_id == job_id))).all()
        vlists = (
            await db.scalars(select(VideoInputList).where(VideoInputList.job_id == job_id))
        ).all()
        elements = (
            await db.scalars(select(StagePlotElement).where(StagePlotElement.job_id == job_id))
        ).all()
        devices = (await db.scalars(select(GraphDevice).where(GraphDevice.job_id == job_id))).all()
        edges = (
            await db.scalars(select(ConnectionEdge).where(ConnectionEdge.job_id == job_id))
        ).all()

    assert {e.graph_source_role for e in elements} == {
        "channel",
        "output_point",
        "video_input",
        None,
    }
    both = [e for e in elements if e.graph_device_id and e.graph_source_id]
    assert len(both) >= 2  # a speaker with an output point and a camera with a video input

    legacy = derive_cables(list(lists), list(elements), list(vlists))
    graph = derive_cables_from_graph(list(devices), list(edges), list(elements))
    assert len(legacy) == len(graph) > 0

    def shape(cables, names):
        return sorted(
            (
                c.key,
                names.get(c.from_device_id),
                names.get(c.to_device_id),
                c.from_element_id,
                c.to_element_id,
            )
            for c in cables
        )

    legacy_names = {str(d.id): d.name for d in (await _legacy_devices(job_id))}
    graph_names = {str(d.id): d.name for d in devices}
    assert shape(legacy, legacy_names) == shape(graph, graph_names)

    plan = {"routes": {str(hidden_point_id): {"hidden": True}}}
    args = {"cable_plan": plan, "audience": [], "stage_offset": (0.0, 0.0)}
    legacy_paths = routed_cable_paths(
        channel_lists=list(lists), elements=list(elements), video_lists=list(vlists), **args
    )
    graph_paths = routed_cable_paths_from_graph(
        devices=list(devices), edges=list(edges), elements=list(elements), **args
    )
    assert len(legacy_paths) > 0
    assert sorted(legacy_paths, key=lambda p: p["key"]) == sorted(
        graph_paths, key=lambda p: p["key"]
    )
    assert str(hidden_point_id) not in {p["key"] for p in graph_paths}


async def _legacy_devices(job_id):
    async with db_mod.SessionLocal() as db:
        return (await db.scalars(select(AudioDevice).where(AudioDevice.job_id == job_id))).all()
