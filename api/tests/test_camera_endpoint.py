from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.main import app

BASE = "/api/v1"


async def test_camera_values_come_from_the_devices_without_stockwire_and_from_stockwire_when_linked(
    auth_headers, monkeypatch
):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Cams"}, headers=auth_headers)
        ).json()["id"]
        cam = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "PTZ 1",
                    "device_type": "camera",
                    "sensor_width_mm": 8.8,
                    "max_distance_m": 15,
                },
                headers=auth_headers,
            )
        ).json()
        lens = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Zoom 12x",
                    "device_type": "lens",
                    "focal_min_mm": 4,
                    "focal_max_mm": 48,
                },
                headers=auth_headers,
            )
        ).json()
        element = (
            await client.post(
                f"{BASE}/jobs/{job_id}/plot-elements",
                json={
                    "element_type": "camera",
                    "label": "PTZ 1",
                    "position_x": 100,
                    "position_y": 50,
                    "linked_device_id": cam["id"],
                    "linked_lens_device_id": lens["id"],
                    "focal_mm": 20,
                },
                headers=auth_headers,
            )
        ).json()
        specs = (
            await client.get(f"{BASE}/jobs/{job_id}/camera-specs", headers=auth_headers)
        ).json()
        assert specs[element["id"]] == {
            "sensor_width_mm": 8.8,
            "focal_min_mm": 4.0,
            "focal_max_mm": 48.0,
            "max_distance_m": 15.0,
            "source": "manual",
            "focal_mm": 20.0,
        }

        async def fake_fetcher(db):
            async def fetch(product_id):
                return {
                    "specs": {
                        "cam_sensor_width_mm": 35,
                        "lens_focal_length_min_mm": 55,
                        "lens_focal_length_max_mm": 200,
                    }
                }

            return fetch

        monkeypatch.setattr(audio_router, "stockwire_product_fetcher", fake_fetcher)
        linked = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{cam['id']}",
            json={"stockwire_product_id": "cam-35"},
            headers=auth_headers,
        )
        assert linked.status_code == 200, linked.text
        specs = (
            await client.get(f"{BASE}/jobs/{job_id}/camera-specs", headers=auth_headers)
        ).json()
        assert specs[element["id"]]["sensor_width_mm"] == 35
        assert specs[element["id"]]["focal_min_mm"] == 55
        assert specs[element["id"]]["source"] == "stockwire"
        assert specs[element["id"]]["focal_mm"] == 55  # 20 mm is outside the Stockwire range
