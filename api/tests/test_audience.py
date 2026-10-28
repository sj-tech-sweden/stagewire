from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"
AUDIENCE = [[100, 200], [900, 200], [900, 700], [100, 700]]


async def test_a_venue_audience_is_copied_into_jobs_on_assign(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(
                f"{BASE}/venues",
                json={
                    "name": "Hall A",
                    "venue_width_cm": 1000,
                    "venue_height_cm": 800,
                    "audience_polygon": AUDIENCE,
                },
                headers=auth_headers,
            )
        ).json()
        assert venue["audience_polygon"] == AUDIENCE
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Show"}, headers=auth_headers)
        ).json()["id"]
        assigned = await client.put(
            f"{BASE}/jobs/{job_id}/venue", json={"venue_id": venue["id"]}, headers=auth_headers
        )
        assert assigned.json()["audience_polygon"] == AUDIENCE


async def test_a_job_can_edit_its_audience_area_and_clear_it(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Edit"}, headers=auth_headers)
        ).json()["id"]
        set_res = await client.patch(
            f"{BASE}/jobs/{job_id}", json={"audience_polygon": AUDIENCE}, headers=auth_headers
        )
        assert set_res.status_code == 200, set_res.text
        assert set_res.json()["audience_polygon"] == AUDIENCE
        cleared = await client.patch(
            f"{BASE}/jobs/{job_id}", json={"audience_polygon": []}, headers=auth_headers
        )
        assert cleared.json()["audience_polygon"] == []


async def test_an_audience_needs_at_least_three_corners(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Bad"}, headers=auth_headers)
        ).json()["id"]
        res = await client.patch(
            f"{BASE}/jobs/{job_id}",
            json={"audience_polygon": [[0, 0], [10, 10]]},
            headers=auth_headers,
        )
        assert res.status_code == 422
