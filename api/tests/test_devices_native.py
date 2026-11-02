"""Devices on the graph: a device is a node (its ``audio_devices:<id>`` ref is its identity) and
the legacy device API, the load tree and the lists read and write that node."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Gear"}, headers=h)).json()["id"]
    return job_id, f"{BASE}/jobs/{job_id}"


async def _nodes(client, h, api):
    return {d["id"]: d for d in (await client.get(f"{api}/graph", headers=h)).json()["devices"]}


@pytest.mark.asyncio
async def test_a_device_is_a_node_with_its_specs_ports_and_domain(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        res = await client.post(
            f"{api}/devices",
            json={
                "name": "Stagebox",
                "device_type": "analog_stagebox",
                "weight_kg": 8,
                "power_watts": 120,
                "ports": [
                    {"direction": "in", "connector": "XLR3", "count": 32},
                    {"direction": "out", "connector": "XLR3", "count": 16},
                ],
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
        dev = res.json()
        node = (await _nodes(client, h, api))[dev["id"]]  # a new device's id is its node id
        assert node["legacy_ref"] == f"audio_devices:{dev['id']}"
        assert (node["kind"], node["domain"], node["name"]) == (
            "analog_stagebox",
            "audio",
            "Stagebox",
        )
        assert node["attributes"]["power_w"] == 120 and node["attributes"]["weight_kg"] == 8
        assert [(p["id"], p["channels"]) for p in node["ports"]] == [
            ("in-xlr3", 32),
            ("out-xlr3", 16),
        ]
        assert [p["count"] for p in dev["ports"]] == [32, 16]

        # a device with a fixture type is lighting; a null clears only the clearable fields
        res = await client.patch(
            f"{api}/devices/{dev['id']}",
            json={"fixture_type": "Spot", "weight_kg": None, "name": None},
            headers=h,
        )
        assert res.status_code == 200, res.text
        node = (await _nodes(client, h, api))[dev["id"]]
        assert node["domain"] == "lighting" and node["name"] == "Stagebox"
        assert (
            "weight_kg" not in node["attributes"] and node["attributes"]["fixture_type"] == "Spot"
        )

        # editing the ports on the graph is editing the connector groups
        res = await client.patch(
            f"{api}/graph/devices/{node['id']}",
            json={
                "ports": [{"id": "in-x", "direction": "in", "signal": "dmx", "connector": "xlr5"}],
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        listed = (await client.get(f"{api}/devices", headers=h)).json()[0]
        assert listed["ports"] == [{"direction": "in", "connector": "xlr5", "count": 0}]


@pytest.mark.asyncio
async def test_a_plain_device_is_a_load_and_its_list_links_clear_with_the_list(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        g = f"{api}/graph"
        amp = (
            await client.post(
                f"{api}/devices",
                json={"name": "Amp", "device_type": "amp", "power_watts": 500},
                headers=h,
            )
        ).json()
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
        point = (await client.post(f"{g}/rigging-points", json={"name": "Truss"}, headers=h)).json()
        res = await client.patch(
            f"{api}/rigging/loads/device/{amp['id']}",
            json={
                "power_node_id": mains["attributes"]["power_id"],
                "power_connector": "schuko",
                "rigging_point_id": point["id"],
            },
            headers=h,
        )
        assert res.status_code == 204, res.text
        node = (await _nodes(client, h, api))[amp["id"]]
        assert node["attributes"]["power_node_id"] == mains["id"]  # the power host's node id
        assert node["attributes"]["rigging_point_id"] == point["id"]
        edges = [
            e for e in (await client.get(g, headers=h)).json()["edges"] if e["signal"] == "power"
        ]
        assert [(e["src_device_id"], e["dst_device_id"]) for e in edges] == [
            (mains["id"], amp["id"])
        ]
        listed = next(
            d
            for d in (await client.get(f"{api}/devices", headers=h)).json()
            if d["id"] == amp["id"]
        )
        assert listed["power_inlet"] == "" and listed["power_watts"] == 500

        # unplugging clears the edge and the connector
        res = await client.patch(
            f"{api}/rigging/loads/device/{amp['id']}", json={"power_node_id": None}, headers=h
        )
        assert res.status_code == 204, res.text
        assert not [
            e for e in (await client.get(g, headers=h)).json()["edges"] if e["signal"] == "power"
        ]

        # a sound list link goes with the list
        lst = (await client.post(f"{api}/channel-lists", json={"name": "FOH"}, headers=h)).json()
        mixer = (
            await client.post(
                f"{api}/devices",
                json={"name": "Desk", "device_type": "mixer", "sound_list_id": lst["id"]},
                headers=h,
            )
        ).json()
        assert mixer["sound_list_id"] == lst["id"]
        assert (
            await client.delete(f"{api}/channel-lists/{lst['id']}", headers=h)
        ).status_code == 204
        listed = {d["id"]: d for d in (await client.get(f"{api}/devices", headers=h)).json()}
        assert listed[mixer["id"]]["sound_list_id"] is None


@pytest.mark.asyncio
async def test_a_catalog_node_becomes_a_device_in_place_and_deleting_a_device_drops_its_node(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, api = await _job(client, h)
        g = f"{api}/graph"
        lst = (await client.post(f"{g}/lists", json={"name": "FOH"}, headers=h)).json()
        ch = (await client.post(f"{g}/lists/{lst['id']}/channels", json={}, headers=h)).json()
        catalog = (
            await client.post(
                f"{g}/devices",
                json={"domain": "audio", "kind": "mixer", "name": "Catalog desk", "ports": []},
                headers=h,
            )
        ).json()
        assert catalog["legacy_ref"] is None
        res = await client.put(
            f"{g}/channels/{ch['id']}/chain",
            json={"steps": [{"device_id": catalog["id"]}]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        node = (await _nodes(client, h, api))[catalog["id"]]
        assert node["legacy_ref"] == f"audio_devices:{catalog['id']}"  # the same node, now a device
        assert [d["id"] for d in (await client.get(f"{api}/devices", headers=h)).json()] == [
            catalog["id"]
        ]
        # it has a patch point, so it cannot be removed until the point goes
        assert (await client.delete(f"{api}/devices/{catalog['id']}", headers=h)).status_code == 409
        res = await client.put(f"{g}/channels/{ch['id']}/chain", json={"steps": []}, headers=h)
        assert res.status_code == 200
        assert (await client.delete(f"{api}/devices/{catalog['id']}", headers=h)).status_code == 204
        assert catalog["id"] not in await _nodes(client, h, api)
