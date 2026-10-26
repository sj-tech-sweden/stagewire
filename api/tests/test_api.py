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
            json={
                "channel_number": 1,
                "source_label": "Kick In",
                "instrument_group": "drums",
                "device": "Beta 52A",
                "stand_type": "Short boom",
            },
        )
        assert channel.status_code == 201
        assert channel.json()["channel_number"] == 1
        assert channel.json()["instrument_group"] == "drums"
        assert channel.json()["device"] == "Beta 52A"
        assert channel.json()["stand_type"] == "Short boom"

        listed = await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{channel.json()['id']}",
            json={
                "input_type": "Microphone",
                "device": "SM58",
                "performer_name": "Alex",
                "wireless_pack": "Beltpack 2",
                "wireless_frequency": "518.125 MHz",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["device"] == "SM58"
        assert updated.json()["performer_name"] == "Alex"
        assert updated.json()["wireless_pack"] == "Beltpack 2"
        assert updated.json()["wireless_frequency"] == "518.125 MHz"

        performer = await client.post(
            f"{BASE}/jobs/{job_id}/plot-elements",
            json={
                "element_type": "performer",
                "label": "Alex on stage",
                "linked_channel_id": channel.json()["id"],
            },
        )
        assert performer.status_code == 201
        assert performer.json()["label"] == "Alex on stage"
        channel_after_link = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels"
        )
        assert channel_after_link.status_code == 200
        assert (
            next(item for item in channel_after_link.json() if item["id"] == channel.json()["id"])[
                "performer_name"
            ]
            == "Alex on stage"
        )

        renamed_performer = await client.patch(
            f"{BASE}/jobs/{job_id}/plot-elements/{performer.json()['id']}",
            json={"label": "Alex stage plot edit"},
        )
        assert renamed_performer.status_code == 200
        channel_after_plot_edit = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels"
        )
        assert (
            next(
                item
                for item in channel_after_plot_edit.json()
                if item["id"] == channel.json()["id"]
            )["performer_name"]
            == "Alex stage plot edit"
        )

        channel_name_edit = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{channel.json()['id']}",
            json={"performer_name": "Alex channel edit"},
        )
        assert channel_name_edit.status_code == 200
        channel_list_after_edit = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels"
        )
        assert (
            next(
                item
                for item in channel_list_after_edit.json()
                if item["id"] == channel.json()["id"]
            )["performer_name"]
            == "Alex channel edit"
        )
        plot_elements = await client.get(f"{BASE}/jobs/{job_id}/plot-elements")
        assert plot_elements.status_code == 200
        assert (
            next(
                element
                for element in plot_elements.json()
                if element["id"] == performer.json()["id"]
            )["label"]
            == "Alex channel edit"
        )
