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
