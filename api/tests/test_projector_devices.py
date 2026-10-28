from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_a_projector_keeps_its_throw_ratio_range_and_can_clear_it(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Projectors"}, headers=auth_headers)
        ).json()["id"]
        projector = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={
                    "name": "Proj 1",
                    "device_type": "projector",
                    "throw_ratio_min": 1.2,
                    "throw_ratio_max": 2.4,
                },
                headers=auth_headers,
            )
        ).json()
        assert (projector["throw_ratio_min"], projector["throw_ratio_max"]) == (1.2, 2.4)

        updated = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{projector['id']}",
            json={"throw_ratio_min": None, "throw_ratio_max": None},
            headers=auth_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["throw_ratio_min"] is None
        assert updated.json()["throw_ratio_max"] is None

        bad = await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{projector['id']}",
            json={"throw_ratio_min": 0},
            headers=auth_headers,
        )
        assert bad.status_code == 422
