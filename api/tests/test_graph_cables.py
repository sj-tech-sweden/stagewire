import pytest
from audio_seed import seed_channel, seed_device, seed_list, seed_output, seed_point
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph import audio_native, devices_native, plot_native
from app.domains.graph.ids import public_id
from app.domains.graph.models import ConnectionEdge, GraphDevice
from app.domains.graph.video_readers import load_video_lists
from app.domains.reports.cable_routing import (
    derive_cables,
    derive_cables_from_graph,
    routed_cable_paths,
    routed_cable_paths_from_graph,
)
from app.main import app

BASE = "/api/v1"


def _element(job_id, kind, x, y, **links):
    """The fields of a plot element (made natively by the seed, as the plot makes them)."""
    return dict(
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
        devices = {}
        for name, kind in (
            ("Stagebox", "analog_stagebox"),
            ("Desk", "mixer"),
            ("Amp", "amp"),
            ("Matrix", "switcher"),
            ("Scaler", "other"),
            ("Camrig", "other"),
            ("Wedge", "monitor"),
        ):
            devices[name] = await seed_device(db, job.id, name=name, device_type=kind)
        await db.commit()
        lst = await seed_list(db, job.id, name="FOH")
        channels = []
        for number in (1, 2):
            ch = await seed_channel(db, lst, channel_number=number, source_label=f"C{number}")
            for position, name in enumerate(("Stagebox", "Desk")):
                await seed_point(db, ch, position=position, device_id=devices[name].id)
            channels.append(ch)
        out = await seed_output(db, lst, name="Mon 1")
        p0 = await seed_point(db, out, position=0, device_id=devices["Desk"].id)
        p1 = await seed_point(db, out, position=1, device_id=devices["Amp"].id)
        p2 = await seed_point(
            db, out, position=2, device_id=devices["Stagebox"].id, parent_id=p0.id
        )
        j = job.id
        for spec in [
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
                linked_device_id=devices["Camrig"].id,
            ),
            _element(j, "projector", 60, 420),
            _element(j, "switcher", 400, 50, linked_device_id=devices["Matrix"].id),
            _element(j, "other", 450, 80, linked_device_id=devices["Scaler"].id),
        ]:
            await plot_native.create_element(db, j, spec)
        await db.commit()
        return job.id, p2.id


@pytest.mark.asyncio
async def test_graph_cables_match_legacy_cables_and_saved_routes(auth_headers):
    job_id, hidden_point_id = await _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(f"{BASE}/jobs/{job_id}/graph/backfill", headers=auth_headers)
        assert res.status_code == 200, res.text
        await _native_video(client, auth_headers, job_id)

    async with db_mod.SessionLocal() as db:
        lists = await audio_native.load_lists(db, job_id)
        vlists = await load_video_lists(db, job_id)
        elements = await plot_native.load_elements(db, job_id)
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
    graph = derive_cables_from_graph(list(devices), list(edges))
    assert len(legacy) == len(graph) > 0

    def shape(cables, names, element_ids):
        return sorted(
            (
                c.key,
                names.get(c.from_device_id),
                names.get(c.to_device_id),
                element_ids.get(c.from_element_id),
                element_ids.get(c.to_element_id),
            )
            for c in cables
        )

    legacy_names = {str(d.id): d.name for d in (await _legacy_devices(job_id))}
    graph_names = {str(d.id): d.name for d in devices}
    legacy_elements = {str(e.id): str(e.id) for e in elements}
    graph_elements = {str(d.id): str(public_id(d)) for d in devices if d.kind == "plot_element"}
    assert shape(legacy, legacy_names, legacy_elements) == shape(graph, graph_names, graph_elements)

    plan = {"routes": {str(hidden_point_id): {"hidden": True}}}
    args = {"cable_plan": plan, "audience": [], "stage_offset": (0.0, 0.0)}
    legacy_paths = routed_cable_paths(
        channel_lists=list(lists), elements=list(elements), video_lists=list(vlists), **args
    )
    graph_paths = routed_cable_paths_from_graph(devices=list(devices), edges=list(edges), **args)
    assert len(legacy_paths) > 0
    assert sorted(legacy_paths, key=lambda p: p["key"]) == sorted(
        graph_paths, key=lambda p: p["key"]
    )
    assert str(hidden_point_id) not in {p["key"] for p in graph_paths}


async def _native_video(client, h, job_id):
    """Video lives only on the graph: a camera chain and an output tree, linked to plot elements."""
    g = f"{BASE}/jobs/{job_id}/graph"
    graph = (await client.get(g, headers=h)).json()
    node = {d["name"]: d for d in graph["devices"] if d["domain"] != "video"}
    lst = (await client.post(f"{g}/video-lists", json={"name": "Video"}, headers=h)).json()
    vin = (
        await client.post(
            f"{g}/video-lists/{lst['id']}/inputs", json={"source_label": "Cam"}, headers=h
        )
    ).json()
    vout = (
        await client.post(
            f"{g}/video-lists/{lst['id']}/outputs", json={"destination_label": "LED"}, headers=h
        )
    ).json()
    steps = [{"device_id": node[n]["id"]} for n in ("Camrig", "Matrix", "Scaler")]
    await client.put(f"{g}/video-inputs/{vin['id']}/chain", json={"steps": steps}, headers=h)
    await client.put(
        f"{g}/video-outputs/{vout['id']}/chain",
        json={
            "steps": [
                {"device_id": node["Matrix"]["id"]},
                {"device_id": node["Scaler"]["id"], "parent_index": 0},
            ]
        },
        headers=h,
    )
    for element_type in ("camera", "projector"):
        el = next(
            d
            for d in graph["devices"]
            if d["kind"] == "plot_element"
            and (d["attributes"] or {}).get("element_type") == element_type
        )
        res = await client.put(
            f"{g}/plot-elements/{el['id']}/links",
            json={"linked_video_input_id": vin["id"]},
            headers=h,
        )
        assert res.status_code == 200, res.text


async def _legacy_devices(job_id):
    async with db_mod.SessionLocal() as db:
        return await devices_native.load_devices(db, job_id)
