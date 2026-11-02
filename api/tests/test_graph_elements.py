import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Elements"}, headers=h)).json()["id"]
    lst = (
        await client.post(f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH"}, headers=h)
    ).json()
    ch = (
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels",
            json={"channel_number": 1, "source_label": "Vox"},
            headers=h,
        )
    ).json()
    box = (
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Stagebox", "device_type": "analog_stagebox"},
            headers=h,
        )
    ).json()
    mic = (
        await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "microphone",
                "label": "Vox mic",
                "position_x": 100,
                "position_y": 200,
                "rotation": 30,
                "width_cm": 40,
                "height_cm": 20,
                "linked_channel_id": ch["id"],
            },
            headers=h,
        )
    ).json()
    stage = (
        await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={"element_type": "stage", "label": "Stage", "linked_device_id": box["id"]},
            headers=h,
        )
    ).json()
    return job_id, ch, box, mic, stage


async def _graph(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()


async def _elements(client, h, job_id):
    rows = (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
    return {r["id"]: r for r in rows}


@pytest.mark.asyncio
async def test_plot_elements_are_graph_nodes_with_link_edges(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, ch, box, mic, stage = await _setup(client, h)
        graph = await _graph(client, h, job_id)
        nodes = {d["name"]: d for d in graph["devices"]}
        node = nodes["Vox mic"]
        assert node["kind"] == "plot_element" and node["ports"] == []
        assert (node["canvas_x_cm"], node["canvas_y_cm"], node["canvas_rotation"]) == (100, 200, 30)
        assert node["attributes"]["element_type"] == "microphone"
        assert node["attributes"]["width_cm"] == 40

        links = [e for e in graph["edges"] if e["signal"] == "link"]
        by_role = {(e["attributes"]["role"], e["src_device_id"]): e for e in links}
        assert by_role[("channel", node["id"])]["dst_device_id"] == nodes["Vox"]["id"]
        assert by_role[("device", nodes["Stage"]["id"])]["dst_device_id"] == nodes["Stagebox"]["id"]

        # links are not signal paths: traces skip them unless asked, and nothing is flagged
        trace = await client.get(
            f"{BASE}/jobs/{job_id}/graph/devices/{node['id']}/trace",
            params={"direction": "downstream"},
            headers=h,
        )
        assert trace.json()["hops"] == []
        explicit = await client.get(
            f"{BASE}/jobs/{job_id}/graph/devices/{node['id']}/trace",
            params={"direction": "downstream", "signal": "link"},
            headers=h,
        )
        assert [x["device_id"] for x in explicit.json()["hops"]] == [nodes["Vox"]["id"]]
        assert (await client.get(f"{BASE}/jobs/{job_id}/graph/validate", headers=h)).json() == []


@pytest.mark.asyncio
async def test_moving_and_renaming_an_element_node_writes_the_plot_element(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, ch, box, mic, stage = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        node = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Vox mic"]

        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "name": "Lead vox",
                "canvas_x_cm": 340,
                "canvas_y_cm": 150,
                "canvas_rotation": 90,
                "attributes": {**node["attributes"], "width_cm": 55},
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        element = (await _elements(client, h, job_id))[mic["id"]]
        assert (element["label"], element["position_x"], element["position_y"]) == (
            "Lead vox",
            340,
            150,
        )
        assert element["rotation"] == 90 and element["width_cm"] == 55
        assert element["linked_channel_id"] == ch["id"]

        # and the legacy plot editor moving it flows back into the node
        await client.patch(
            f"{BASE}/jobs/{job_id}/plot-elements/{mic['id']}",
            json={"position_x": 10, "position_y": 20},
            headers=h,
        )
        moved = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Lead vox"]
        assert (moved["canvas_x_cm"], moved["canvas_y_cm"]) == (10, 20)


@pytest.mark.asyncio
async def test_elements_can_be_created_linked_unlinked_and_deleted_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, ch, box, mic, stage = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        nodes = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}

        created = await client.post(
            f"{g}/devices",
            json={
                "domain": "other",
                "kind": "plot_element",
                "name": "Riser",
                "canvas_x_cm": 50,
                "canvas_y_cm": 60,
                "attributes": {"element_type": "riser", "width_cm": 200, "height_cm": 100},
            },
            headers=h,
        )
        assert created.status_code == 201, created.text
        riser = created.json()
        elements = await _elements(client, h, job_id)
        made = next(e for e in elements.values() if e["label"] == "Riser")
        assert (made["element_type"], made["position_x"], made["width_cm"]) == ("riser", 50, 200)

        link = await client.post(
            f"{g}/edges",
            json={
                "signal": "link",
                "src_device_id": riser["id"],
                "src_port": "link",
                "dst_device_id": nodes["Stagebox"]["id"],
                "dst_port": "device",
            },
            headers=h,
        )
        assert link.status_code == 201, link.text
        assert (await _elements(client, h, job_id))[made["id"]]["linked_device_id"] == box["id"]

        wrong = await client.post(
            f"{g}/edges",
            json={
                "signal": "link",
                "src_device_id": riser["id"],
                "src_port": "link",
                "dst_device_id": nodes["Stagebox"]["id"],
                "dst_port": "channel",
            },
            headers=h,
        )
        assert wrong.status_code == 422

        removed = await client.delete(
            f"{g}/edges/{link.json()['id']}",
            params={"expected_revision": link.json()["revision"]},
            headers=h,
        )
        assert removed.status_code == 204
        assert (await _elements(client, h, job_id))[made["id"]]["linked_device_id"] is None

        riser = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Riser"]
        gone = await client.delete(
            f"{g}/devices/{riser['id']}", params={"expected_revision": riser["revision"]}, headers=h
        )
        assert gone.status_code == 204
        assert made["id"] not in await _elements(client, h, job_id)


@pytest.mark.asyncio
async def test_element_links_are_set_and_cleared_with_legacy_ids_and_labels_can_be_emptied(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, ch, box, mic, _stage = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        graph = (await client.get(g, headers=h)).json()
        node = next(
            d for d in graph["devices"] if d["legacy_ref"] == f"stage_plot_elements:{mic['id']}"
        )

        res = await client.put(
            f"{g}/plot-elements/{node['id']}/links",
            json={"linked_device_id": box["id"], "linked_channel_id": None},
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = next(
            e
            for e in (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
            if e["id"] == mic["id"]
        )
        assert legacy["linked_device_id"] == box["id"] and legacy["linked_channel_id"] is None
        links = {
            e["attributes"]["role"]: e["attributes"]["legacy_target"]
            for e in (await client.get(g, headers=h)).json()["edges"]
            if e["signal"] == "link"
        }
        assert links == {"device": box["id"]}

        other = await client.post(f"{BASE}/jobs", json={"title": "Other"}, headers=h)
        stranger = (
            await client.post(
                f"{BASE}/jobs/{other.json()['id']}/devices",
                json={"name": "Elsewhere", "device_type": "other"},
                headers=h,
            )
        ).json()
        every = await client.put(
            f"{g}/plot-elements/{node['id']}/links",
            json={"linked_channel_id": ch["id"], "linked_device_id": box["id"]},
            headers=h,
        )
        assert every.status_code == 200, every.text
        roles = {
            e["attributes"]["role"]
            for e in (await client.get(g, headers=h)).json()["edges"]
            if e["signal"] == "link"
        }
        assert roles == {"channel", "device"}
        refused = await client.put(
            f"{g}/plot-elements/{node['id']}/links",
            json={"linked_device_id": stranger["id"]},
            headers=h,
        )
        assert refused.status_code == 422

        wrong = await client.put(
            f"{g}/plot-elements/{box['id']}/links", json={"linked_device_id": None}, headers=h
        )
        assert wrong.status_code == 404

        node = next(
            d for d in (await client.get(g, headers=h)).json()["devices"] if d["id"] == node["id"]
        )
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={"attributes": {"label": ""}, "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = next(
            e
            for e in (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
            if e["id"] == mic["id"]
        )
        assert legacy["label"] == ""
        assert res.json()["name"] == "microphone"


@pytest.mark.asyncio
async def test_a_plot_element_created_with_an_empty_label_keeps_it_empty(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Empty"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        res = await client.post(
            f"{g}/devices",
            json={
                "domain": "other",
                "kind": "plot_element",
                "name": "custom",
                "attributes": {"element_type": "custom", "label": ""},
                "canvas_x_cm": 10,
                "canvas_y_cm": 20,
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
        assert [e["label"] for e in legacy] == [""]


@pytest.mark.asyncio
async def test_every_link_role_validates_and_links(auth_headers, monkeypatch):
    from app.domains.audio import router as audio_router

    async def none(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", none)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, ch, box, mic, _stage = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        graph = await _graph(client, h, job_id)
        by_ref = {d["legacy_ref"]: d for d in graph["devices"]}
        element = by_ref[f"stage_plot_elements:{mic['id']}"]
        list_node = next(d for d in graph["devices"] if d["kind"] == "channel_list")
        ch_node = by_ref[f"audio_channel_patches:{ch['id']}"]
        box_node = by_ref[f"audio_devices:{box['id']}"]

        out = (
            await client.post(
                f"{g}/lists/{list_node['id']}/outputs", json={"name": "Main"}, headers=h
            )
        ).json()
        for chain in (f"channels/{ch_node['id']}", f"outputs/{out['id']}"):
            res = await client.put(
                f"{g}/{chain}/chain", json={"steps": [{"device_id": box_node["id"]}]}, headers=h
            )
            assert res.status_code == 200, res.text
        lists = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()
        patch_point = lists[0]["channels"][0]["patch_points"][0]["id"]
        output_point = lists[0]["outputs"][0]["points"][0]["id"]

        vlist = (await client.post(f"{g}/video-lists", json={}, headers=h)).json()
        vin = (
            await client.post(f"{g}/video-lists/{vlist['id']}/inputs", json={}, headers=h)
        ).json()
        video_input = vin["id"]  # video nodes have no legacy row: the public id is the node id
        source = (
            await client.post(
                f"{g}/power-nodes",
                json={"kind": "source", "feed_connector": "cee63_3p", "rating_amps": 63},
                headers=h,
            )
        ).json()
        point = (await client.post(f"{g}/rigging-points", json={"name": "T"}, headers=h)).json()

        res = await client.put(
            f"{g}/plot-elements/{element['id']}/links",
            json={
                "linked_patch_point_id": patch_point,
                "linked_output_point_id": output_point,
                "linked_video_input_id": video_input,
                "linked_lens_device_id": box["id"],
                "power_node_id": source["legacy_ref"].split(":")[1],
                "rigging_point_id": point["id"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        roles = {
            e["attributes"]["role"]: e["attributes"]["legacy_target"]
            for e in (await _graph(client, h, job_id))["edges"]
            if e["signal"] == "link"
        }
        assert roles["patch_point"] == patch_point and roles["output_point"] == output_point
        assert roles["video_input"] == video_input and roles["lens"] == box["id"]
        assert res.json()["attributes"]["rigging_point_id"] == point["id"]

        for column in ("linked_patch_point_id", "linked_output_point_id", "linked_video_input_id"):
            bad = await client.put(
                f"{g}/plot-elements/{element['id']}/links",
                json={column: "00000000-0000-0000-0000-000000000001"},
                headers=h,
            )
            assert bad.status_code == 422, column
