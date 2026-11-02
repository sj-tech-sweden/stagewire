"""Video lists authored on the graph: the behaviour the old per-table endpoints used to cover."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _setup(client, h, title="Video"):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": title}, headers=h)).json()["id"]
    g = f"{BASE}/jobs/{job_id}/graph"
    lst = (await client.post(f"{g}/video-lists", json={"name": "Cams"}, headers=h)).json()
    return job_id, g, lst


async def _device(client, g, h, name, device_type="other"):
    return (
        await client.post(
            f"{g}/audio-devices", json={"name": name, "device_type": device_type}, headers=h
        )
    ).json()


def _legacy_id(node):
    return node["legacy_ref"].partition(":")[2]


async def _lists(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/video-lists", headers=h)).json()


async def _input(client, g, h, lst, label="Cam 1", **extra):
    return (
        await client.post(
            f"{g}/video-lists/{lst['id']}/inputs", json={"source_label": label, **extra}, headers=h
        )
    ).json()


@pytest.mark.asyncio
async def test_an_input_chain_is_replaced_in_order_and_a_projector_is_refused(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        cam = await _device(client, g, h, "PTZ 1", "ptz_camera")
        bay = await _device(client, g, h, "Patchbay A", "patchbay")
        sw = await _device(client, g, h, "ATEM", "switcher")
        proj = await _device(client, g, h, "Projector", "projector")
        inp = await _input(client, g, h, lst)

        steps = [
            {"device_id": cam["id"], "connector": "sdi", "patch_label": "Cam 1"},
            {"device_id": bay["id"], "connector": "sdi", "patch_label": "A1", "input_port": "In 3"},
            {"device_id": sw["id"], "connector": "sdi", "patch_label": "3"},
        ]
        res = await client.put(
            f"{g}/video-inputs/{inp['id']}/chain", json={"steps": steps}, headers=h
        )
        assert res.status_code == 200, res.text
        points = (await _lists(client, h, job_id))[0]["inputs"][0]["patch_points"]
        assert [p["device_id"] for p in points] == [_legacy_id(d) for d in (cam, bay, sw)]
        assert [p["patch_label"] for p in points] == ["Cam 1", "A1", "3"]
        assert points[1]["input_port"] == "In 3"

        # replacing the chain replaces every point
        await client.put(
            f"{g}/video-inputs/{inp['id']}/chain",
            json={"steps": [{"device_id": sw["id"]}, {"device_id": cam["id"]}]},
            headers=h,
        )
        points = (await _lists(client, h, job_id))[0]["inputs"][0]["patch_points"]
        assert [p["device_id"] for p in points] == [_legacy_id(sw), _legacy_id(cam)]

        refused = await client.put(
            f"{g}/video-inputs/{inp['id']}/chain",
            json={"steps": [{"device_id": proj["id"]}]},
            headers=h,
        )
        assert refused.status_code == 422
        out = (
            await client.post(
                f"{g}/video-lists/{lst['id']}/outputs", json={"name": "PGM"}, headers=h
            )
        ).json()
        ok = await client.put(
            f"{g}/video-outputs/{out['id']}/chain",
            json={"steps": [{"device_id": sw["id"]}, {"device_id": proj["id"], "parent_index": 0}]},
            headers=h,
        )
        assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_an_output_can_split_and_the_reader_keeps_the_tree(auth_headers):
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
        left = await _device(client, g, h, "Left", "screen")
        right = await _device(client, g, h, "Right", "screen")
        res = await client.put(
            f"{g}/video-outputs/{out['id']}/chain",
            json={
                "steps": [
                    {"device_id": sw["id"], "connector": "SDI"},
                    {"device_id": split["id"], "parent_index": 0, "input_port": "A"},
                    {"device_id": left["id"], "parent_index": 1},
                    {"device_id": right["id"], "parent_index": 1, "notes": "far side"},
                ]
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        points = (await _lists(client, h, job_id))[0]["outputs"][0]["patch_points"]
        by_device = {p["device_id"]: p for p in points}
        assert len(points) == 4
        assert by_device[_legacy_id(sw)]["parent_id"] is None
        assert by_device[_legacy_id(split)]["parent_id"] == by_device[_legacy_id(sw)]["id"]
        assert by_device[_legacy_id(left)]["parent_id"] == by_device[_legacy_id(split)]["id"]
        assert by_device[_legacy_id(right)]["notes"] == "far side"
        # the web app reads the roots from the node and the rest from edges
        graph = (await client.get(g, headers=h)).json()
        node = next(d for d in graph["devices"] if d["id"] == out["id"])
        assert [r["device_id"] for r in node["attributes"]["roots"]] == [sw["id"]]
        assert node["ports"][0]["channels"] == 2  # two leaves feed the destination

        # deleting the splitter's connection hands its children to its parent
        edges = [e for e in graph["edges"] if e["dst_device_id"] == split["id"]]
        gone = edges[0]
        assert (
            await client.delete(
                f"{g}/edges/{gone['id']}", params={"expected_revision": gone["revision"]}, headers=h
            )
        ).status_code == 204
        points = (await _lists(client, h, job_id))[0]["outputs"][0]["patch_points"]
        assert len(points) == 3
        assert {p["parent_id"] for p in points if p["device_id"] != _legacy_id(sw)} == {
            next(p["id"] for p in points if p["device_id"] == _legacy_id(sw))
        }


@pytest.mark.asyncio
async def test_rows_number_from_a_start_and_a_node_rename_is_the_label(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        batch = await client.post(
            f"{g}/video-lists/{lst['id']}/inputs/batch",
            json=[{"input_number": 5, "source_label": "A"}, {"source_label": "B"}],
            headers=h,
        )
        assert [n["attributes"]["input_number"] for n in batch.json()] == [5, 6]
        outs = await client.post(
            f"{g}/video-lists/{lst['id']}/outputs/batch",
            json=[{"name": "PGM"}, {"name": "AUX", "destination_label": "Wall"}],
            headers=h,
        )
        assert [n["attributes"]["output_number"] for n in outs.json()] == [1, 2]

        node = batch.json()[0]
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={"name": "Wide", "position": 9, "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        row = (await _lists(client, h, job_id))[0]["inputs"][-1]
        assert (row["source_label"], row["input_number"]) == ("Wide", 9)

        # the switcher product of a list is set and cleared on the list node
        lst = next(
            d for d in (await client.get(g, headers=h)).json()["devices"] if d["id"] == lst["id"]
        )
        res = await client.patch(
            f"{g}/devices/{lst['id']}",
            json={
                "attributes": {"switcher_product_id": "77", "switcher_product_name": "ATEM"},
                "expected_revision": lst["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200
        assert (await _lists(client, h, job_id))[0]["switcher_product_id"] == "77"
        res = await client.patch(
            f"{g}/devices/{lst['id']}",
            json={
                "attributes": {"switcher_product_id": None, "switcher_product_name": None},
                "expected_revision": res.json()["revision"],
            },
            headers=h,
        )
        assert (await _lists(client, h, job_id))[0]["switcher_product_id"] is None


@pytest.mark.asyncio
async def test_a_list_follows_its_switcher(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        lst = (
            await client.patch(
                f"{g}/devices/{lst['id']}",
                json={
                    "attributes": {
                        "switcher_product_id": "777",
                        "switcher_product_name": "ATEM Mini",
                        "switcher_inputs": 4,
                        "switcher_outputs": 2,
                    },
                    "expected_revision": lst["revision"],
                },
                headers=h,
            )
        ).json()
        kept = await _input(client, g, h, lst, "Kept")
        await _input(client, g, h, lst, "Free")
        other = await _device(client, g, h, "Other", "converter")
        await client.put(
            f"{g}/video-inputs/{kept['id']}/chain",
            json={"steps": [{"device_id": other["id"]}]},
            headers=h,
        )
        await client.post(f"{g}/video-lists/{lst['id']}/outputs", json={"name": "PGM"}, headers=h)

        res = await client.post(f"{g}/video-lists/{lst['id']}/fill-from-switcher", headers=h)
        assert res.status_code == 200, res.text
        result = res.json()
        assert (result["inputs_added"], result["inputs_patched"]) == (2, 1)
        assert (result["outputs_added"], result["outputs_patched"]) == (1, 1)

        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
        switcher = next(d for d in devices if d["device_type"] == "switcher")
        assert switcher["stockwire_product_id"] == "777" and switcher["id"] == result["device_id"]
        listed = (await _lists(client, h, job_id))[0]
        assert [i["input_number"] for i in listed["inputs"]] == [1, 2, 3, 4]
        assert listed["inputs"][0]["patch_points"][0]["device_id"] == _legacy_id(other)
        assert listed["inputs"][1]["patch_points"][0]["device_id"] == switcher["id"]
        assert [o["patch_points"][0]["device_id"] for o in listed["outputs"]] == [
            switcher["id"]
        ] * 2

        # a second run changes nothing and reuses the switcher
        again = (
            await client.post(f"{g}/video-lists/{lst['id']}/fill-from-switcher", headers=h)
        ).json()
        assert again["device_id"] == result["device_id"]
        assert (again["inputs_added"], again["outputs_added"]) == (0, 0)
        # each list gets its own switcher, named after it, and a device can be told its list
        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
        assert [d["video_list_id"] for d in devices if d["device_type"] == "switcher"] == [
            lst["id"]
        ]


@pytest.mark.asyncio
async def test_links_sheets_and_deletes_follow_the_video_nodes(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        inp = await _input(client, g, h, lst)
        sw = await _device(client, g, h, "ATEM", "switcher")
        await client.put(
            f"{g}/video-inputs/{inp['id']}/chain",
            json={"steps": [{"device_id": sw["id"], "connector": "sdi", "patch_label": "3"}]},
            headers=h,
        )

        # one sheet per device, listing what goes through it
        sheets = (await client.get(f"{BASE}/jobs/{job_id}/video-patch-sheets", headers=h)).json()
        assert [s["name"] for s in sheets] == ["ATEM"]
        assert (
            sheets[0]["rows"][0]["label"] == "Cam 1" and sheets[0]["rows"][0]["patch_label"] == "3"
        )

        # a camera on the plot links to the input by its public id and unlinks again
        element = (
            await client.post(
                f"{BASE}/jobs/{job_id}/plot-elements",
                json={"element_type": "camera", "label": "Cam A"},
                headers=h,
            )
        ).json()
        node = next(
            d
            for d in (await client.get(g, headers=h)).json()["devices"]
            if d["kind"] == "plot_element"
        )
        link = await client.put(
            f"{g}/plot-elements/{node['id']}/links",
            json={"linked_video_input_id": inp["id"]},
            headers=h,
        )
        assert link.status_code == 200, link.text
        els = (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
        assert (
            next(e for e in els if e["id"] == element["id"])["linked_video_input_id"] == inp["id"]
        )
        bad = await client.put(
            f"{g}/plot-elements/{node['id']}/links",
            json={"linked_video_input_id": lst["id"]},
            headers=h,
        )
        assert bad.status_code == 422

        # a device with a video connection cannot be deleted
        assert (
            await client.delete(f"{BASE}/jobs/{job_id}/devices/{_legacy_id(sw)}", headers=h)
        ).status_code == 409

        # deleting the input clears the plot link; deleting the list removes its rows
        graph = (await client.get(g, headers=h)).json()
        node_in = next(d for d in graph["devices"] if d["id"] == inp["id"])
        res = await client.delete(
            f"{g}/devices/{inp['id']}", params={"expected_revision": node_in["revision"]}, headers=h
        )
        assert res.status_code == 204
        els = (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
        assert next(e for e in els if e["id"] == element["id"])["linked_video_input_id"] is None
        assert (await _lists(client, h, job_id))[0]["inputs"] == []
        # the device is free again
        assert (
            await client.delete(f"{BASE}/jobs/{job_id}/devices/{_legacy_id(sw)}", headers=h)
        ).status_code == 204

        second = await _input(client, g, h, lst, "Cam 2")
        graph = (await client.get(g, headers=h)).json()
        node_list = next(d for d in graph["devices"] if d["id"] == lst["id"])
        assert (
            await client.delete(
                f"{g}/devices/{lst['id']}",
                params={"expected_revision": node_list["revision"]},
                headers=h,
            )
        ).status_code == 204
        graph = (await client.get(g, headers=h)).json()
        assert second["id"] not in {d["id"] for d in graph["devices"]}
        assert await _lists(client, h, job_id) == []


@pytest.mark.asyncio
async def test_a_signal_traces_from_a_camera_through_the_matrix_to_the_destination(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, lst = await _setup(client, h)
        cam = await _input(client, g, h, lst)
        out = (
            await client.post(
                f"{g}/video-lists/{lst['id']}/outputs",
                json={"destination_label": "LED wall"},
                headers=h,
            )
        ).json()
        matrix = await _device(client, g, h, "Matrix", "switcher")
        scaler = await _device(client, g, h, "Scaler")
        led = await _device(client, g, h, "LED proc")
        await client.put(
            f"{g}/video-inputs/{cam['id']}/chain",
            json={"steps": [{"device_id": matrix["id"], "input_port": "In 3"}]},
            headers=h,
        )
        await client.put(
            f"{g}/video-outputs/{out['id']}/chain",
            json={
                "steps": [
                    {"device_id": matrix["id"]},
                    {"device_id": scaler["id"], "parent_index": 0, "source_port": "Out 1"},
                    {"device_id": led["id"], "parent_index": 1},
                ]
            },
            headers=h,
        )
        graph = (await client.get(g, headers=h)).json()
        by_name = {d["name"]: d for d in graph["devices"]}
        trace = await client.get(
            f"{g}/devices/{cam['id']}/trace", params={"direction": "downstream"}, headers=h
        )
        assert out["id"] in {hop["device_id"] for hop in trace.json()["hops"]}
        assert any(p["id"] == "In 3" for p in by_name["Matrix"]["ports"])
        assert any(p["id"] == "Out 1" for p in by_name["Matrix"]["ports"])
        assert not any(p["id"] == "Out 1" for p in by_name["Scaler"]["ports"])
