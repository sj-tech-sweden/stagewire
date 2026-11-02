"""Power nodes on the graph: a node that is a device lives on the device's node, extra feeds are
edges, and the sync and the engine's rules keep them intact."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Power"}, headers=h)).json()["id"]
    g = f"{BASE}/jobs/{job_id}/graph"

    async def post(path, body, status=201):
        res = await client.post(f"{g}/{path}", json=body, headers=h)
        assert res.status_code == status, res.text
        return res.json()

    mains = await post(
        "power-nodes",
        {
            "name": "Mains",
            "kind": "source",
            "feed_connector": "cee63_3p",
            "rating_amps": 63,
            "outputs": [{"connector": "cee32_3p", "count": 2}],
        },
    )
    box = await post("audio-devices", {"name": "Breakout box", "device_type": "other"})
    return job_id, g, post, mains, box


@pytest.mark.asyncio
async def test_a_power_node_for_a_device_lives_on_the_devices_own_node(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, mains, box = await _setup(client, h)
        node = await post(
            "power-nodes",
            {
                "name": "Box power",
                "kind": "breakout",
                "parent_id": mains["id"],
                "feed_connector": "cee32_3p",
                "outputs": [{"connector": "schuko", "count": 4}],
                "device_id": box["id"],
            },
        )
        # the same node as the device, not a second one
        assert node["id"] == box["id"]
        assert node["attributes"]["power_id"] and node["attributes"]["outputs"][0]["count"] == 4
        graph = (await client.get(g, headers=h)).json()
        assert sum(1 for d in graph["devices"] if d["name"] == "Breakout box") == 1
        feed = [
            e for e in graph["edges"] if e["signal"] == "power" and e["dst_device_id"] == box["id"]
        ]
        assert len(feed) == 1 and feed[0]["src_device_id"] == mains["id"]

        # a sync keeps the power side of the device node and its feed edge (same edge id)
        await client.post(f"{g}/backfill", headers=h)
        graph = (await client.get(g, headers=h)).json()
        again = next(d for d in graph["devices"] if d["id"] == box["id"])
        assert again["attributes"]["power_id"] == node["attributes"]["power_id"]
        kept = [
            e for e in graph["edges"] if e["signal"] == "power" and e["dst_device_id"] == box["id"]
        ]
        assert [e["id"] for e in kept] == [feed[0]["id"]]
        assert any(p["direction"] == "in" and p["signal"] == "power" for p in again["ports"])

        # the summary lists it by the device node, and gear can be plugged into it
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert box["id"] in {n["id"] for n in summary["nodes"]}

        # it cannot be deleted while something hangs from it
        await post(
            "power-nodes",
            {
                "name": "Strip",
                "kind": "breakout",
                "parent_id": node["id"],
                "feed_connector": "schuko",
                "outputs": [{"connector": "schuko", "count": 2}],
            },
        )
        current = next(
            d for d in (await client.get(g, headers=h)).json()["devices"] if d["id"] == box["id"]
        )
        res = await client.delete(
            f"{g}/devices/{box['id']}", params={"expected_revision": current["revision"]}, headers=h
        )
        assert res.status_code == 409


@pytest.mark.asyncio
async def test_extra_feeds_are_edges_that_can_be_edited_and_removed(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, mains, box = await _setup(client, h)
        other = await post(
            "power-nodes",
            {
                "name": "Second mains",
                "kind": "source",
                "feed_connector": "cee63_3p",
                "rating_amps": 63,
                "outputs": [{"connector": "cee32_3p", "count": 1}],
            },
        )
        node = await post(
            "power-nodes",
            {
                "name": "Distro",
                "kind": "distro",
                "parent_id": mains["id"],
                "feed_connector": "cee32_3p",
                "outputs": [{"connector": "schuko", "count": 4}],
            },
        )
        res = await client.post(
            f"{g}/power-nodes/{node['id']}/feeds",
            json={"parent_id": other["id"], "feed_connector": "cee32_3p"},
            headers=h,
        )
        assert res.status_code == 201, res.text
        graph = (await client.get(g, headers=h)).json()
        feeds = [
            e for e in graph["edges"] if e["signal"] == "power" and e["dst_device_id"] == node["id"]
        ]
        assert len(feeds) == 2

        extra = next(e for e in feeds if e["src_device_id"] == other["id"])
        res = await client.patch(
            f"{g}/edges/{extra['id']}",
            json={"phase": "L2", "expected_revision": extra["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy_feeds = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        mine = next(n for n in legacy_feeds if n["name"] == "Distro")
        assert [f["phase"] for f in mine["feeds"]] == ["L2"]

        # the node's own feed cannot be cut; the extra one can
        own = next(e for e in feeds if e["src_device_id"] == mains["id"])
        res = await client.delete(
            f"{g}/edges/{own['id']}", params={"expected_revision": own["revision"]}, headers=h
        )
        assert res.status_code == 409
        extra = next(
            e
            for e in (await client.get(g, headers=h)).json()["edges"]
            if e["signal"] == "power" and e["src_device_id"] == other["id"]
        )
        res = await client.delete(
            f"{g}/edges/{extra['id']}",
            params={"expected_revision": extra["revision"]},
            headers=h,
        )
        assert res.status_code == 204, res.text
        mine = next(
            n
            for n in (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
            if n["name"] == "Distro"
        )
        assert mine["feeds"] == []
