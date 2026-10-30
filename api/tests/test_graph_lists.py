import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h):
    return (await client.post(f"{BASE}/jobs", json={"title": "Lists"}, headers=h)).json()["id"]


@pytest.mark.asyncio
async def test_a_channel_list_can_be_authored_entirely_through_the_graph_api(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        lst = await client.post(f"{g}/lists", json={"name": "FOH", "mixer_inputs": 32}, headers=h)
        assert lst.status_code == 201, lst.text
        assert lst.json()["kind"] == "channel_list"
        list_id = lst.json()["id"]

        first = await client.post(
            f"{g}/lists/{list_id}/channels", json={"source_label": "Kick"}, headers=h
        )
        assert first.status_code == 201, first.text
        assert first.json()["attributes"]["channel_number"] == 1
        batch = await client.post(
            f"{g}/lists/{list_id}/channels/batch",
            json=[{"source_label": "Snare"}, {"channel_number": 10, "source_label": "Vox"}],
            headers=h,
        )
        assert [c["attributes"]["channel_number"] for c in batch.json()] == [2, 10]

        # a catalog item with no legacy twin is made patchable on demand
        stagebox = (
            await client.post(
                f"{g}/devices",
                json={"domain": "audio", "name": "Stagebox", "stockwire_product_id": "12"},
                headers=h,
            )
        ).json()
        desk = (
            await client.post(f"{g}/devices", json={"domain": "audio", "name": "Desk"}, headers=h)
        ).json()
        chain = await client.put(
            f"{g}/channels/{first.json()['id']}/chain",
            json={
                "steps": [
                    {"device_id": stagebox["id"], "connector": "XLR", "patch_label": "In 3"},
                    {"device_id": desk["id"], "connector": "Dante"},
                ]
            },
            headers=h,
        )
        assert chain.status_code == 200, chain.text
        edges = chain.json()["edges"]
        assert [e["attributes"]["patch_label"] for e in edges] == ["In 3", ""]
        assert [e["attributes"]["position"] for e in edges] == [0, 1]

        out = await client.post(f"{g}/lists/{list_id}/outputs", json={"name": "Mon 1"}, headers=h)
        assert out.status_code == 201
        amp = (
            await client.post(f"{g}/devices", json={"domain": "audio", "name": "Amp"}, headers=h)
        ).json()
        bad = await client.put(
            f"{g}/outputs/{out.json()['id']}/chain",
            json={"steps": [{"device_id": desk["id"], "parent_index": 0}]},
            headers=h,
        )
        assert bad.status_code == 422
        ok = await client.put(
            f"{g}/outputs/{out.json()['id']}/chain",
            json={
                "steps": [
                    {"device_id": desk["id"]},
                    {"device_id": amp["id"], "connector": "XLR"},
                    {"device_id": stagebox["id"], "parent_index": 0},
                ]
            },
            headers=h,
        )
        assert ok.status_code == 200, ok.text
        assert len(ok.json()["edges"]) == 3  # console->bus plus two chain edges

        # the shadow rows exist, so the unmoved readers and the legacy editor see the same list
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()
        assert [c["source_label"] for c in legacy[0]["channels"]] == ["Kick", "Snare", "Vox"]
        assert len(legacy[0]["channels"][0]["patch_points"]) == 2
        assert [p["device_id"] is not None for p in legacy[0]["outputs"][0]["points"]] == [True] * 3
        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
        assert {d["name"] for d in devices} == {"Stagebox", "Desk", "Amp"}

        csv = await client.get(
            f"{g}/lists/{list_id}/export", params={"plugin": "generic_csv"}, headers=h
        )
        assert csv.status_code == 200

        # replacing a chain replaces it
        again = await client.put(
            f"{g}/channels/{first.json()['id']}/chain",
            json={"steps": [{"device_id": desk["id"]}]},
            headers=h,
        )
        assert len(again.json()["edges"]) == 1
        sheets = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()
        assert len(sheets[0]["channels"][0]["patch_points"]) == 1


@pytest.mark.asyncio
async def test_list_endpoints_reject_the_wrong_kind_of_node(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        node = (
            await client.post(f"{g}/devices", json={"domain": "audio", "name": "Mic"}, headers=h)
        ).json()
        assert (
            await client.post(f"{g}/lists/{node['id']}/channels", json={}, headers=h)
        ).status_code == 404
        assert (
            await client.put(f"{g}/channels/{node['id']}/chain", json={"steps": []}, headers=h)
        ).status_code == 404
