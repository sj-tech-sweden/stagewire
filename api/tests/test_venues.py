import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"

VENUE = {
    "name": "Main Hall",
    "venue_width_cm": 1000,
    "venue_height_cm": 800,
    "stage_x_cm": 100,
    "stage_y_cm": 50,
    "stage_width_cm": 300,
    "stage_height_cm": 200,
    "background_image_url": "/static/hall.png",
}


async def test_venue_crud_and_validation(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)
        assert created.status_code == 201, created.text
        venue_id = created.json()["id"]
        assert created.json()["venue_width_cm"] == 1000
        assert created.json()["propagated_at"] is None

        listed = await client.get(f"{BASE}/venues", headers=auth_headers)
        assert listed.status_code == 200
        assert any(v["id"] == venue_id for v in listed.json())

        updated = await client.patch(
            f"{BASE}/venues/{venue_id}",
            json={"stage_x_cm": 150, "notes": "Load-in at the back"},
            headers=auth_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["stage_x_cm"] == 150
        assert updated.json()["venue_width_cm"] == 1000

        invalid = await client.post(
            f"{BASE}/venues", json={**VENUE, "venue_width_cm": -5}, headers=auth_headers
        )
        assert invalid.status_code == 422

        missing = await client.get(
            f"{BASE}/venues/00000000-0000-0000-0000-000000000000", headers=auth_headers
        )
        assert missing.status_code == 404

        deleted = await client.delete(f"{BASE}/venues/{venue_id}", headers=auth_headers)
        assert deleted.status_code == 204


async def test_assign_snapshots_venue_and_unassign_keeps_it(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)).json()
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Gig A"}, headers=auth_headers)
        ).json()

        assigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": venue["id"]},
            headers=auth_headers,
        )
        assert assigned.status_code == 200, assigned.text
        body = assigned.json()
        assert body["venue_id"] == venue["id"]
        assert body["venue_name"] == "Main Hall"
        assert body["venue_width_cm"] == 1000
        assert body["venue_height_cm"] == 800
        assert body["stage_x_cm"] == 100
        assert body["stage_y_cm"] == 50
        assert body["stage_width_cm"] == 300
        assert body["stage_height_cm"] == 200
        assert body["venue_background_image_url"] == "/static/hall.png"

        unassigned = await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": None}, headers=auth_headers
        )
        assert unassigned.status_code == 200
        assert unassigned.json()["venue_id"] is None
        assert unassigned.json()["venue_width_cm"] == 1000

        missing = await client.put(
            f"{BASE}/jobs/{job['id']}/venue",
            json={"venue_id": "00000000-0000-0000-0000-000000000000"},
            headers=auth_headers,
        )
        assert missing.status_code == 404


async def test_deleting_venue_keeps_job_snapshot(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)).json()
        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Gig B"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": venue["id"]}, headers=auth_headers
        )

        await client.delete(f"{BASE}/venues/{venue['id']}", headers=auth_headers)

        after = (await client.get(f"{BASE}/jobs/{job['id']}", headers=auth_headers)).json()
        assert after["venue_id"] is None
        assert after["venue_width_cm"] == 1000
        assert after["stage_width_cm"] == 300


async def test_propagate_all_and_newer(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (await client.post(f"{BASE}/venues", json=VENUE, headers=auth_headers)).json()
        venue_id = venue["id"]

        old_job = (
            await client.post(f"{BASE}/jobs", json={"title": "Old"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{old_job['id']}/venue",
            json={"venue_id": venue_id},
            headers=auth_headers,
        )

        first = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        assert first.status_code == 200, first.text
        assert first.json() == {"updated": 1}

        venue_after_propagate = (
            await client.get(f"{BASE}/venues/{venue_id}", headers=auth_headers)
        ).json()
        assert venue_after_propagate["propagated_at"] is not None

        await asyncio.sleep(0.01)
        new_job = (
            await client.post(f"{BASE}/jobs", json={"title": "New"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{new_job['id']}/venue",
            json={"venue_id": venue_id},
            headers=auth_headers,
        )

        await client.patch(
            f"{BASE}/venues/{venue_id}",
            json={"venue_width_cm": 1200, "stage_width_cm": 400},
            headers=auth_headers,
        )

        newer = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "newer"}, headers=auth_headers
        )
        assert newer.status_code == 200, newer.text
        assert newer.json() == {"updated": 1}

        old_after = (await client.get(f"{BASE}/jobs/{old_job['id']}", headers=auth_headers)).json()
        new_after = (await client.get(f"{BASE}/jobs/{new_job['id']}", headers=auth_headers)).json()
        assert old_after["venue_width_cm"] == 1000
        assert old_after["stage_width_cm"] == 300
        assert new_after["venue_width_cm"] == 1200
        assert new_after["stage_width_cm"] == 400

        everyone = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "all"}, headers=auth_headers
        )
        assert everyone.json() == {"updated": 2}
        old_final = (await client.get(f"{BASE}/jobs/{old_job['id']}", headers=auth_headers)).json()
        assert old_final["venue_width_cm"] == 1200

        bad_scope = await client.post(
            f"{BASE}/venues/{venue_id}/propagate", json={"scope": "some"}, headers=auth_headers
        )
        assert bad_scope.status_code == 422
