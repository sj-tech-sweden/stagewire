from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def test_health_live() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"{BASE}/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_auth_flow() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        setup = await client.post(
            f"{BASE}/auth/setup",
            json={"email": "a@test.local", "password": "pw", "first_name": "A", "last_name": "B"},
        )
        assert setup.status_code == 201
        banned = await client.post(
            f"{BASE}/auth/setup", json={"email": "x@test.local", "password": "pw"}
        )
        assert banned.status_code == 409
        login = await client.post(
            f"{BASE}/auth/login", json={"email": "a@test.local", "password": "pw"}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        me = await client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "a@test.local"


async def test_jobs_require_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"{BASE}/jobs")
    assert resp.status_code == 401


async def test_create_and_list_job(auth_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers
    ) as client:
        created = await client.post(
            f"{BASE}/jobs", json={"title": "Test Show", "venue_name": "The Hall"}
        )
        assert created.status_code == 201
        job_id = created.json()["id"]

        fetched = await client.get(f"{BASE}/jobs/{job_id}")
        assert fetched.status_code == 200
        assert fetched.json()["title"] == "Test Show"

        ch_list = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists",
            json={"name": "FOH", "position": 0},
        )
        assert ch_list.status_code == 201
        list_id = ch_list.json()["id"]

        channel = await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
            json={"channel_number": 1, "source_label": "Kick In"},
        )
        assert channel.status_code == 201
        assert channel.json()["channel_number"] == 1

        listed = await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{channel.json()['id']}",
            json={"input_type": "Microphone", "device": "SM58"},
        )
        assert updated.status_code == 200
        assert updated.json()["device"] == "SM58"
