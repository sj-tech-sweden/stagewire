"""Stage plot elements on the graph: no legacy table behind them, and the same behaviour the
plot, the load tree and the reports had when the table was the storage."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h, title="Plot"):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": title}, headers=h)).json()["id"]
    return job_id, f"{BASE}/jobs/{job_id}"


async def _nodes(client, h, job_id):
    return {
        d["id"]: d
        for d in (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()["devices"]
    }


async def _elements(client, h, job_id):
    rows = (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
    return {r["id"]: r for r in rows}


@pytest.mark.asyncio
async def test_an_element_is_a_node_of_its_own_and_its_label_and_name_stay_in_step(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        el = (
            await client.post(
                f"{api}/plot-elements",
                json={"element_type": "speaker", "label": "Main L", "position_x": 10},
                headers=h,
            )
        ).json()
        node = (await _nodes(client, h, job_id))[el["id"]]  # the element id is the node id
        assert node["legacy_ref"] is None and node["kind"] == "plot_element"
        assert (node["name"], node["attributes"]["label"], node["canvas_x_cm"]) == (
            "Main L",
            "Main L",
            10,
        )
        assert node["attributes"]["width_cm"] == 60  # the defaults the old row had

        # a rename on the graph is the new label...
        res = await client.patch(
            f"{api}/graph/devices/{node['id']}",
            json={"name": "Main Left", "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert (await _elements(client, h, job_id))[el["id"]]["label"] == "Main Left"
        # ...and the plot's own edit moves the node name
        await client.patch(f"{api}/plot-elements/{el['id']}", json={"label": "Stage L"}, headers=h)
        assert (await _nodes(client, h, job_id))[el["id"]]["name"] == "Stage L"
        # an empty label leaves the type as the name; a null size keeps the default
        res = await client.patch(
            f"{api}/graph/devices/{node['id']}",
            json={
                "attributes": {"label": "", "width_cm": None},
                "expected_revision": (await _nodes(client, h, job_id))[el["id"]]["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        node = (await _nodes(client, h, job_id))[el["id"]]
        assert (node["name"], node["attributes"]["width_cm"]) == ("speaker", 60)

        res = await client.delete(f"{api}/plot-elements/{el['id']}", headers=h)
        assert res.status_code == 204
        assert el["id"] not in await _nodes(client, h, job_id)
        assert (
            await client.delete(f"{api}/plot-elements/{el['id']}", headers=h)
        ).status_code == 404


@pytest.mark.asyncio
async def test_a_performer_label_and_its_channels_performer_name_follow_each_other(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        lst = (await client.post(f"{api}/channel-lists", json={"name": "FOH"}, headers=h)).json()
        ch = (
            await client.post(
                f"{api}/channel-lists/{lst['id']}/channels",
                json={"channel_number": 1, "source_label": "Vox"},
                headers=h,
            )
        ).json()
        el = (
            await client.post(
                f"{api}/plot-elements",
                json={"element_type": "performer", "label": "Alex", "linked_channel_id": ch["id"]},
                headers=h,
            )
        ).json()

        def channel_of(lists):
            return lists[0]["channels"][0]

        lists = (await client.get(f"{api}/channel-lists", headers=h)).json()
        assert channel_of(lists)["performer_name"] == "Alex"
        await client.patch(f"{api}/plot-elements/{el['id']}", json={"label": "Alexa"}, headers=h)
        lists = (await client.get(f"{api}/channel-lists", headers=h)).json()
        assert channel_of(lists)["performer_name"] == "Alexa"

        res = await client.patch(
            f"{api}/channels/{ch['id']}",
            json={"performer_name": "Sam", "expected_revision": channel_of(lists)["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert (await _elements(client, h, job_id))[el["id"]]["label"] == "Sam"
        assert (await _nodes(client, h, job_id))[el["id"]]["name"] == "Sam"


@pytest.mark.asyncio
async def test_a_link_follows_its_target_and_goes_when_the_target_is_deleted(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        box = (
            await client.post(
                f"{api}/devices", json={"name": "Box", "device_type": "analog_stagebox"}, headers=h
            )
        ).json()
        el = (
            await client.post(
                f"{api}/plot-elements",
                json={"element_type": "stage", "linked_device_id": box["id"]},
                headers=h,
            )
        ).json()
        graph = (await client.get(f"{api}/graph", headers=h)).json()
        links = [e for e in graph["edges"] if e["signal"] == "link"]
        assert [(e["attributes"]["role"], e["attributes"]["legacy_target"]) for e in links] == [
            ("device", box["id"])
        ]
        row = (await _elements(client, h, job_id))[el["id"]]
        assert row["graph_device_id"] == links[0]["dst_device_id"]

        # the device goes; what the foreign key's ON DELETE SET NULL did, the sync does now
        assert (await client.delete(f"{api}/devices/{box['id']}", headers=h)).status_code == 204
        row = (await _elements(client, h, job_id))[el["id"]]
        assert row["linked_device_id"] is None and row["graph_device_id"] is None
        graph = (await client.get(f"{api}/graph", headers=h)).json()
        assert not [e for e in graph["edges"] if e["signal"] == "link"]


@pytest.mark.asyncio
async def test_an_element_is_a_load_on_a_rigging_point_and_a_power_node(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        g = f"{api}/graph"
        amp = (
            await client.post(
                f"{api}/devices",
                json={"name": "Amp", "device_type": "amp", "weight_kg": 6, "power_watts": 400},
                headers=h,
            )
        ).json()
        el = (
            await client.post(
                f"{api}/plot-elements",
                json={"element_type": "speaker", "label": "Main", "linked_device_id": amp["id"]},
                headers=h,
            )
        ).json()
        point = (await client.post(f"{g}/rigging-points", json={"name": "Truss"}, headers=h)).json()
        mains = (
            await client.post(
                f"{g}/power-nodes",
                json={
                    "name": "Mains",
                    "kind": "source",
                    "feed_connector": "cee32_3p",
                    "rating_amps": 32,
                    "outputs": [{"connector": "schuko", "count": 2}],
                },
                headers=h,
            )
        ).json()
        power_id = mains["attributes"]["power_id"]

        res = await client.patch(
            f"{api}/rigging/loads/element/{el['id']}",
            json={
                "rigging_point_id": point["id"],
                "power_node_id": power_id,
                "power_connector": "schuko",
            },
            headers=h,
        )
        assert res.status_code == 204, res.text
        node = (await _nodes(client, h, job_id))[el["id"]]
        # the node holds the graph ids of the point and the power host, the way fixtures do
        assert node["attributes"]["rigging_point_id"] == point["id"]
        assert node["attributes"]["power_node_id"] == mains["id"]
        roles = {
            e["attributes"]["role"]
            for e in (await client.get(g, headers=h)).json()["edges"]
            if e["signal"] == "link" and e["src_device_id"] == node["id"]
        }
        assert roles == {"device", "power_node"}
        summary = (await client.get(f"{api}/rigging/summary", headers=h)).json()
        assert any(
            load["id"] == el["id"] and load["power_node_id"] == power_id
            for load in summary["loads"]
        )

        # a point that goes takes the hang with it; unplugging clears the connector
        node = (await _nodes(client, h, job_id))[point["id"]]
        assert (
            await client.delete(
                f"{g}/devices/{point['id']}",
                params={"expected_revision": node["revision"]},
                headers=h,
            )
        ).status_code == 204
        node = (await _nodes(client, h, job_id))[el["id"]]
        assert "rigging_point_id" not in node["attributes"]
        res = await client.patch(
            f"{api}/rigging/loads/element/{el['id']}", json={"power_node_id": None}, headers=h
        )
        assert res.status_code == 204, res.text
        node = (await _nodes(client, h, job_id))[el["id"]]
        assert "power_node_id" not in node["attributes"]
        assert node["attributes"]["power_connector"] == ""
