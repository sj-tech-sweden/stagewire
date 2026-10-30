import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _graph(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()


async def _legacy(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()


@pytest.mark.asyncio
async def test_fixtures_are_authored_and_edited_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Lights"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"

        wash = await client.post(
            f"{g}/fixtures",
            json={
                "device_name": "Wash 1",
                "fixture_type": "LED wash",
                "footprint": 16,
                "purpose": "FOH",
            },
            headers=h,
        )
        assert wash.status_code == 201, wash.text
        wash = wash.json()
        assert wash["name"] == "Wash 1" and wash["domain"] == "lighting"
        assert wash["attributes"]["dmx_address"] == 1 and wash["attributes"]["universe"] == 1

        spot = (
            await client.post(
                f"{g}/fixtures",
                json={"fixture_type": "Spot", "footprint": 8, "purpose": "Back"},
                headers=h,
            )
        ).json()
        assert spot["kind"] == "fixture" and spot["attributes"]["dmx_address"] == 17

        # moving the spot onto the wash's channels is flagged by the legacy DMX check
        res = await client.patch(
            f"{g}/devices/{spot['id']}",
            json={
                "attributes": {**spot["attributes"], "dmx_address": 10},
                "expected_revision": spot["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        flags = {f["purpose"]: f["dmx_conflict"] for f in await _legacy(client, h, job_id)}
        assert flags == {"FOH": True, "Back": True}

        # editing the fixture on the device's node reaches the fixture row, not just the device
        res = await client.patch(
            f"{g}/devices/{wash['id']}",
            json={
                "attributes": {**wash["attributes"], "dmx_address": 100, "location": "Truss 1"},
                "expected_revision": wash["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = {f["purpose"]: f for f in await _legacy(client, h, job_id)}
        assert legacy["FOH"]["dmx_address"] == 100 and legacy["FOH"]["location"] == "Truss 1"
        assert legacy["FOH"]["dmx_conflict"] is False and legacy["Back"]["dmx_conflict"] is False

        # deleting the fixture-only node removes the fixture; deleting the device node removes both
        spot = next(d for d in (await _graph(client, h, job_id))["devices"] if d["name"] == "Back")
        assert (
            await client.delete(
                f"{g}/devices/{spot['id']}",
                params={"expected_revision": spot["revision"]},
                headers=h,
            )
        ).status_code == 204
        assert [f["purpose"] for f in await _legacy(client, h, job_id)] == ["FOH"]
        wash = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["name"] == "Wash 1"
        )
        assert (
            await client.delete(
                f"{g}/devices/{wash['id']}",
                params={"expected_revision": wash["revision"]},
                headers=h,
            )
        ).status_code == 204
        assert await _legacy(client, h, job_id) == []
        assert (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json() == []


@pytest.mark.asyncio
async def test_bulk_add_lays_out_kinds_one_after_another_and_rolls_into_the_next_universe(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Bulk"}, headers=h)).json()["id"]
        g = f"{BASE}/jobs/{job_id}/graph"
        res = await client.post(
            f"{g}/fixtures/bulk",
            json={
                "universe": 1,
                "start_address": 1,
                "spacing": 0,
                "items": [
                    {
                        "fixture_type": "Wash",
                        "channel_mode": "16ch",
                        "footprint": 16,
                        "quantity": 3,
                    },
                    {
                        "fixture_type": "Spot",
                        "channel_mode": "40ch",
                        "footprint": 40,
                        "quantity": 2,
                        "label": "Key",
                    },
                ],
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
        assert len(res.json()) == 5
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()
        placed = [(f["purpose"], f["universe"], f["dmx_address"], f["footprint"]) for f in legacy]
        assert placed == [
            ("Wash 1", 1, 1, 16),
            ("Wash 2", 1, 17, 16),
            ("Wash 3", 1, 33, 16),
            ("Key 1", 1, 49, 40),
            ("Key 2", 1, 89, 40),
        ]
        assert {
            t["name"]
            for t in (await client.get(f"{BASE}/jobs/{job_id}/fixture-types", headers=h)).json()
        } == {"Wash", "Spot"}

        wrap = await client.post(
            f"{g}/fixtures/bulk",
            json={
                "universe": 2,
                "start_address": 500,
                "items": [{"fixture_type": "Wash", "channel_mode": "16ch", "quantity": 2}],
            },
            headers=h,
        )
        assert wrap.status_code == 201, wrap.text
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()
        tail = [(f["universe"], f["dmx_address"]) for f in legacy[-2:]]
        assert tail == [(3, 1), (3, 17)]

        free = await client.post(
            f"{g}/fixtures/bulk",
            json={
                "universe": 1,
                "items": [{"fixture_type": "Spot", "channel_mode": "40ch", "quantity": 2}],
            },
            headers=h,
        )
        assert free.status_code == 201
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()
        assert [(f["universe"], f["dmx_address"]) for f in legacy[-2:]] == [(1, 129), (1, 169)]

        too_many = await client.post(
            f"{g}/fixtures/bulk",
            json={
                "items": [
                    {"fixture_type": "Wash", "quantity": 200},
                    {"fixture_type": "Spot", "quantity": 200},
                ]
            },
            headers=h,
        )
        assert too_many.status_code == 422
