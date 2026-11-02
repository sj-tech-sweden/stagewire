import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h):
    return (await client.post(f"{BASE}/jobs", json={"title": "Devices"}, headers=h)).json()["id"]


@pytest.mark.asyncio
async def test_a_device_with_ports_and_specs_is_created_and_edited_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        created = await client.post(
            f"{g}/audio-devices",
            json={
                "name": "Cam 1",
                "device_type": "camera",
                "sensor_width_mm": 9.6,
                "focal_min_mm": 4.3,
                "focal_max_mm": 86,
                "weight_kg": 2.5,
                "ports": [{"direction": "out", "connector": "SDI", "count": 2}],
            },
            headers=h,
        )
        assert created.status_code == 201, created.text
        node = created.json()
        assert node["domain"] == "video" and node["kind"] == "camera"
        assert node["attributes"]["sensor_width_mm"] == 9.6
        assert node["ports"][0]["id"] == "out-sdi" and node["ports"][0]["channels"] == 2

        # editing specs and ports in the graph writes the legacy row
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "name": "Cam 1 FOH",
                "kind": "ptz_camera",
                "attributes": {**node["attributes"], "focal_max_mm": 120, "max_distance_m": None},
                "ports": [
                    {"id": "out-sdi", "direction": "out", "connector": "SDI", "channels": 2},
                    {"id": "in-hdmi", "direction": "in", "connector": "HDMI", "channels": 1},
                    {"id": "out-video", "direction": "out", "signal": "video"},
                ],
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()[0]
        assert (legacy["name"], legacy["device_type"], legacy["focal_max_mm"]) == (
            "Cam 1 FOH",
            "ptz_camera",
            120,
        )
        assert legacy["ports"] == [
            {"direction": "out", "connector": "SDI", "count": 2},
            {"direction": "in", "connector": "HDMI", "count": 1},
        ]
        refreshed = {d["name"]: d for d in (await client.get(g, headers=h)).json()["devices"]}
        assert {p["id"] for p in refreshed["Cam 1 FOH"]["ports"]} >= {"out-sdi", "in-hdmi"}


@pytest.mark.asyncio
async def test_effective_values_report_overrides_and_sources(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        mixer = (
            await client.post(
                f"{g}/audio-devices",
                json={"name": "Desk", "device_type": "mixer", "weight_kg": 12, "power_watts": 300},
                headers=h,
            )
        ).json()
        node = mixer
        await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "attributes": {**node["attributes"], "input_override": 48},
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        values = (await client.get(f"{g}/effective", headers=h)).json()[node["id"]]
        assert values["input_count"] == 48 and values["input_source"] == "override"
        assert values["weight_kg_effective"] == 12 and values["weight_source"] == "manual"
        assert values["power_watts_effective"] == 300
