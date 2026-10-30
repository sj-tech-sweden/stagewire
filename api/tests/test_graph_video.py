import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _graph(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()


async def _legacy(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=h)).json()


async def _device(client, g, h, name, device_type="other"):
    return (
        await client.post(
            f"{g}/audio-devices", json={"name": name, "device_type": device_type}, headers=h
        )
    ).json()


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Video"}, headers=h)).json()["id"]
    g = f"{BASE}/jobs/{job_id}/graph"
    lst = (await client.post(f"{g}/video-lists", json={"name": "Cams"}, headers=h)).json()
    return job_id, g, lst


@pytest.mark.asyncio
async def test_video_lists_inputs_and_outputs_are_authored_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        assert lst["kind"] == "video_list" and lst["domain"] == "video"

        first = await client.post(
            f"{g}/video-lists/{lst['id']}/inputs", json={"source_label": "Cam 1"}, headers=h
        )
        assert first.status_code == 201, first.text
        assert first.json()["kind"] == "video_input"
        assert first.json()["attributes"]["input_number"] == 1
        assert first.json()["attributes"]["list_id"] == lst["id"]
        batch = await client.post(
            f"{g}/video-lists/{lst['id']}/inputs/batch",
            json=[{"source_label": "Cam 2"}, {"source_label": "Cam 3", "connector": "hdmi"}],
            headers=h,
        )
        assert [n["attributes"]["input_number"] for n in batch.json()] == [2, 3]
        out = await client.post(
            f"{g}/video-lists/{lst['id']}/outputs",
            json={"destination_label": "Screen L"},
            headers=h,
        )
        assert out.status_code == 201, out.text
        assert out.json()["kind"] == "video_destination"

        legacy = (await _legacy(client, h, job_id))[0]
        assert [i["source_label"] for i in legacy["inputs"]] == ["Cam 1", "Cam 2", "Cam 3"]
        assert legacy["inputs"][2]["connector"] == "hdmi"
        assert legacy["outputs"][0]["destination_label"] == "Screen L"

        missing = await client.post(
            f"{g}/video-lists/{first.json()['id']}/inputs", json={}, headers=h
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_a_video_input_chain_is_replaced_and_projectors_are_refused(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        cam = (
            await client.post(
                f"{g}/video-lists/{lst['id']}/inputs", json={"source_label": "Cam 1"}, headers=h
            )
        ).json()
        sw = await _device(client, g, h, "Switcher", "switcher")
        conv = await _device(client, g, h, "Converter", "converter")
        proj = await _device(client, g, h, "Projector", "projector")

        res = await client.put(
            f"{g}/video-inputs/{cam['id']}/chain",
            json={
                "steps": [
                    {"device_id": conv["id"], "connector": "SDI"},
                    {"device_id": sw["id"], "connector": "HDMI", "input_port": "In 1"},
                ]
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert [e["attributes"]["position"] for e in res.json()["edges"]] == [0, 1]
        points = (await _legacy(client, h, job_id))[0]["inputs"][0]["patch_points"]
        assert [p["connector"] for p in points] == ["SDI", "HDMI"]
        assert points[1]["input_port"] == "In 1"

        bad = await client.put(
            f"{g}/video-inputs/{cam['id']}/chain",
            json={"steps": [{"device_id": proj["id"]}]},
            headers=h,
        )
        assert bad.status_code == 422
        assert len((await _legacy(client, h, job_id))[0]["inputs"][0]["patch_points"]) == 2


@pytest.mark.asyncio
async def test_a_video_output_chain_branches_and_keeps_its_roots_on_the_node(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        out = (
            await client.post(
                f"{g}/video-lists/{lst['id']}/outputs", json={"name": "PGM"}, headers=h
            )
        ).json()
        sw = await _device(client, g, h, "Switcher", "switcher")
        split = await _device(client, g, h, "Splitter", "split")
        screen = await _device(client, g, h, "Screen", "screen")
        bad = await client.put(
            f"{g}/video-outputs/{out['id']}/chain",
            json={"steps": [{"device_id": sw["id"], "parent_index": 0}]},
            headers=h,
        )
        assert bad.status_code == 422

        res = await client.put(
            f"{g}/video-outputs/{out['id']}/chain",
            json={
                "steps": [
                    {"device_id": sw["id"], "connector": "SDI"},
                    {"device_id": split["id"], "parent_index": 0},
                    {"device_id": screen["id"], "parent_index": 1},
                ]
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        node = next(d for d in (await _graph(client, h, job_id))["devices"] if d["id"] == out["id"])
        roots = node["attributes"]["roots"]
        assert len(roots) == 1 and roots[0]["device_id"] == sw["id"]
        assert roots[0]["connector"] == "SDI"
        points = (await _legacy(client, h, job_id))[0]["outputs"][0]["patch_points"]
        assert [p["parent_id"] is None for p in points] == [True, False, False]


@pytest.mark.asyncio
async def test_video_node_and_edge_edits_and_deletes_write_through(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        cam = (
            await client.post(
                f"{g}/video-lists/{lst['id']}/inputs", json={"source_label": "Cam 1"}, headers=h
            )
        ).json()
        out = (
            await client.post(
                f"{g}/video-lists/{lst['id']}/outputs", json={"name": "PGM"}, headers=h
            )
        ).json()
        sw = await _device(client, g, h, "Switcher", "switcher")
        conv = await _device(client, g, h, "Converter", "converter")
        await client.put(
            f"{g}/video-inputs/{cam['id']}/chain",
            json={"steps": [{"device_id": conv["id"]}, {"device_id": sw["id"]}]},
            headers=h,
        )

        res = await client.patch(
            f"{g}/devices/{cam['id']}",
            json={
                "name": "Wide",
                "attributes": {"source_type": "computer"},
                "expected_revision": cam["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await _legacy(client, h, job_id))[0]
        assert (legacy["inputs"][0]["source_label"], legacy["inputs"][0]["source_type"]) == (
            "Wide",
            "computer",
        )
        res = await client.patch(
            f"{g}/devices/{lst['id']}",
            json={"name": "Main cams", "expected_revision": lst["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        res = await client.patch(
            f"{g}/devices/{out['id']}",
            json={
                "attributes": {"destination_label": "Screen R"},
                "expected_revision": out["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await _legacy(client, h, job_id))[0]
        assert legacy["name"] == "Main cams"
        assert legacy["outputs"][0]["destination_label"] == "Screen R"

        edges = [
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if (e["attributes"] or {}).get("point_id")
        ]
        first = next(e for e in edges if e["attributes"]["position"] == 0)
        res = await client.patch(
            f"{g}/edges/{first['id']}",
            json={"attributes": {"connector": "BNC"}, "expected_revision": first["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert (await _legacy(client, h, job_id))[0]["inputs"][0]["patch_points"][0][
            "connector"
        ] == "BNC"
        res = await client.delete(
            f"{g}/edges/{first['id']}",
            params={"expected_revision": first["revision"] + 1},
            headers=h,
        )
        assert res.status_code in (204, 409)

        node = {d["id"]: d for d in (await _graph(client, h, job_id))["devices"]}[out["id"]]
        assert (
            await client.delete(
                f"{g}/devices/{node['id']}",
                params={"expected_revision": node["revision"]},
                headers=h,
            )
        ).status_code == 204
        assert (await _legacy(client, h, job_id))[0]["outputs"] == []
        node = {d["id"]: d for d in (await _graph(client, h, job_id))["devices"]}[lst["id"]]
        assert (
            await client.delete(
                f"{g}/devices/{node['id']}",
                params={"expected_revision": node["revision"]},
                headers=h,
            )
        ).status_code == 204
        assert await _legacy(client, h, job_id) == []


@pytest.mark.asyncio
async def test_many_video_inputs_can_share_a_switchers_generic_input_port(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        sw = await _device(client, g, h, "Switcher", "switcher")
        for n in range(3):
            cam = (
                await client.post(
                    f"{g}/video-lists/{lst['id']}/inputs",
                    json={"source_label": f"Cam {n}"},
                    headers=h,
                )
            ).json()
            res = await client.put(
                f"{g}/video-inputs/{cam['id']}/chain",
                json={"steps": [{"device_id": sw["id"]}]},
                headers=h,
            )
            assert res.status_code == 200, res.text
        issues = (await client.get(f"{g}/validate", headers=h)).json()
        assert [i for i in issues if i["code"] == "port_in_use"] == []

        a = (
            await client.post(
                f"{g}/devices",
                json={
                    "domain": "video",
                    "name": "A",
                    "ports": [{"id": "o", "direction": "out", "signal": "video"}],
                },
                headers=h,
            )
        ).json()
        b = (
            await client.post(
                f"{g}/devices",
                json={
                    "domain": "video",
                    "name": "B",
                    "ports": [{"id": "i", "direction": "in", "signal": "video"}],
                },
                headers=h,
            )
        ).json()
        edge = {
            "signal": "video",
            "src_device_id": a["id"],
            "src_port": "o",
            "dst_device_id": b["id"],
            "dst_port": "i",
        }
        assert (await client.post(f"{g}/edges", json=edge, headers=h)).status_code == 201
        other = (
            await client.post(
                f"{g}/devices",
                json={
                    "domain": "video",
                    "name": "C",
                    "ports": [{"id": "o", "direction": "out", "signal": "video"}],
                },
                headers=h,
            )
        ).json()
        second = await client.post(
            f"{g}/edges", json={**edge, "src_device_id": other["id"]}, headers=h
        )
        assert second.status_code == 422
