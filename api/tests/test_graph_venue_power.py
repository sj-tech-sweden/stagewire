import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _venue_job(client, h):
    venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Venue power"}, headers=h)).json()[
        "id"
    ]
    res = await client.put(f"{BASE}/jobs/{job_id}/venue", json={"venue_id": venue["id"]}, headers=h)
    assert res.status_code in (200, 201), res.text
    return venue["id"], job_id


@pytest.mark.asyncio
async def test_a_power_group_becomes_one_source_with_an_output_per_outlet(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue_id, job_id = await _venue_job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        group = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-groups",
                json={"name": "Stage left", "rating_amps": 16, "phases": 1},
                headers=h,
            )
        ).json()
        outlets = []
        for n in range(3):
            res = await client.post(
                f"{BASE}/venues/{venue_id}/power-outlets",
                json={"name": f"SL {n + 1}", "connector": "schuko", "group_id": group["id"]},
                headers=h,
            )
            assert res.status_code == 201, res.text
            outlets.append(res.json())
        single = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-outlets",
                json={"name": "Wall", "connector": "cee16", "rating_amps": 16},
                headers=h,
            )
        ).json()

        first = await client.post(f"{g}/venue-power/outlets/{outlets[0]['id']}/source", headers=h)
        assert first.status_code == 200, first.text
        node = first.json()["node"]
        assert node["kind"] == "source" and node["name"] == "Stage left"
        assert first.json()["connector"] == "schuko"
        # the second outlet of the group is served by the same source
        second = await client.post(f"{g}/venue-power/outlets/{outlets[1]['id']}/source", headers=h)
        assert second.json()["node"]["id"] == node["id"]
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        source = next(n for n in nodes if n["name"] == "Stage left")
        assert source["rating_amps"] == 16
        assert source["outputs"] == [{"connector": "schuko", "count": 3, "phase": "L1"}]

        # an outlet added to the group later is picked up the next time the group is used
        extra = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-outlets",
                json={"name": "SL 4", "connector": "schuko", "group_id": group["id"]},
                headers=h,
            )
        ).json()
        await client.post(f"{g}/venue-power/outlets/{extra['id']}/source", headers=h)
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        assert next(n for n in nodes if n["name"] == "Stage left")["outputs"][0]["count"] == 4

        # a device is plugged into the group: it counts on the group's source
        gear = (
            await client.post(
                f"{g}/audio-devices",
                json={"name": "Amp", "device_type": "other", "power_watts": 600},
                headers=h,
            )
        ).json()
        res = await client.put(
            f"{g}/loads/{gear['id']}",
            json={"power_node_id": node["id"], "power_connector": "schuko"},
            headers=h,
        )
        assert res.status_code == 200, res.text

        # an outlet without a group gets a source of its own
        alone = await client.post(f"{g}/venue-power/outlets/{single['id']}/source", headers=h)
        assert alone.status_code == 200, alone.text
        assert alone.json()["node"]["name"] == "Wall" and alone.json()["connector"] == "cee16"


@pytest.mark.asyncio
async def test_power_groups_are_validated(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue_id, job_id = await _venue_job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        unrated = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-groups", json={"name": "No rating"}, headers=h
            )
        ).json()
        outlet = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-outlets",
                json={"name": "X", "connector": "schuko", "group_id": unrated["id"]},
                headers=h,
            )
        ).json()
        res = await client.post(f"{g}/venue-power/outlets/{outlet['id']}/source", headers=h)
        assert res.status_code == 422 and "rating" in res.text

        elsewhere = (await client.post(f"{BASE}/venues", json={"name": "Other"}, headers=h)).json()
        foreign = await client.post(
            f"{BASE}/venues/{elsewhere['id']}/power-outlets",
            json={"name": "F", "connector": "schuko", "group_id": unrated["id"]},
            headers=h,
        )
        assert foreign.status_code == 422
        stranger = (
            await client.post(
                f"{BASE}/venues/{elsewhere['id']}/power-outlets",
                json={"name": "F", "connector": "schuko"},
                headers=h,
            )
        ).json()
        res = await client.post(f"{g}/venue-power/outlets/{stranger['id']}/source", headers=h)
        assert res.status_code == 404
        blank = await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets", json={"name": "Bare"}, headers=h
        )
        assert blank.status_code == 422
        gone = await client.delete(
            f"{BASE}/venues/{venue_id}/power-groups/{unrated['id']}", headers=h
        )
        assert gone.status_code == 204
        outlets = (await client.get(f"{BASE}/venues/{venue_id}/power-outlets", headers=h)).json()
        assert outlets[0]["group_id"] is None


@pytest.mark.asyncio
async def test_a_one_phase_group_carries_its_whole_load_on_one_phase_and_gear_can_hang(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue_id, job_id = await _venue_job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        group = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-groups",
                json={"name": "Wall", "rating_amps": 10, "phases": 1},
                headers=h,
            )
        ).json()
        outlet = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-outlets",
                json={"name": "W1", "connector": "schuko", "group_id": group["id"]},
                headers=h,
            )
        ).json()
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={"name": "W2", "connector": "schuko", "group_id": group["id"]},
            headers=h,
        )
        source = (
            await client.post(f"{g}/venue-power/outlets/{outlet['id']}/source", headers=h)
        ).json()
        point = (
            await client.post(f"{g}/rigging-points", json={"name": "Truss A"}, headers=h)
        ).json()
        for name, watts in (("Projector", 100), ("LED wall", 3500)):
            gear = (
                await client.post(
                    f"{g}/audio-devices",
                    json={
                        "name": name,
                        "device_type": "other",
                        "power_watts": watts,
                        "weight_kg": 40,
                    },
                    headers=h,
                )
            ).json()
            res = await client.put(
                f"{g}/loads/{gear['id']}",
                json={
                    "power_node_id": source["node"]["id"],
                    "power_connector": "schuko",
                    "rigging_point_id": point["id"],
                },
                headers=h,
            )
            assert res.status_code == 200, res.text
            assert res.json()["attributes"]["rigging_point_id"] == point["id"]
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        node = next(n for n in summary["nodes"] if n["name"] == "Wall")
        # 3600 W on one phase of a 10 A group is 15.7 A: over its rating, not a third of it
        assert node["amps"]["L1"] == 15.65 and node["amps"]["L2"] == 0
        assert node["status"] == "over" and node["percent"] > 150
        assert next(p for p in summary["points"] if p["name"] == "Truss A")["load_kg"] == 80

        load = (await client.get(f"{g}/power-load", headers=h)).json()
        assert load["L1"] == 3600 and load["L2"] == 0 and load["L3"] == 0
        # one phase is all this supply can feed, so there is no imbalance to report
        assert load["imbalance_pct"] == 0
        # the gear on the overloaded group is over too, not "ok"
        assert {row["power_status"] for row in summary["loads"]} == {"over"}
