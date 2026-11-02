import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _make_channel(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, dict]:
    job = await client.post(f"{BASE}/jobs", json={"title": "Conflict Job"}, headers=headers)
    job_id = job.json()["id"]
    lst = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "Main"}, headers=headers
    )
    list_id = lst.json()["id"]
    channel = await client.post(
        f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels",
        json={"channel_number": 1, "source_label": "Kick"},
        headers=headers,
    )
    assert channel.status_code == 201, channel.text
    return job_id, list_id, channel.json()


@pytest.mark.asyncio
async def test_stale_channel_update_returns_409_with_current_row(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, _, channel = await _make_channel(client, auth_headers)
        url = f"{BASE}/jobs/{job_id}/channels/{channel['id']}"
        assert channel["revision"] == 1

        first = await client.patch(
            url, json={"source_label": "Kick In", "expected_revision": 1}, headers=auth_headers
        )
        assert first.status_code == 200, first.text
        assert first.json()["revision"] == 2

        stale = await client.patch(
            url, json={"source_label": "Kick Out", "expected_revision": 1}, headers=auth_headers
        )
        assert stale.status_code == 409
        detail = stale.json()["detail"]
        assert detail["code"] == "revision_conflict"
        assert detail["current"]["source_label"] == "Kick In"
        assert detail["current"]["revision"] == 2


@pytest.mark.asyncio
async def test_stale_channel_delete_returns_409_and_keeps_row(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, list_id, channel = await _make_channel(client, auth_headers)
        url = f"{BASE}/jobs/{job_id}/channels/{channel['id']}"
        await client.patch(
            url, json={"source_label": "Kick In", "expected_revision": 1}, headers=auth_headers
        )

        stale = await client.delete(url, params={"expected_revision": 1}, headers=auth_headers)
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "revision_conflict"

        listed = await client.get(
            f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels", headers=auth_headers
        )
        assert len(listed.json()) == 1

        ok = await client.delete(url, params={"expected_revision": 2}, headers=auth_headers)
        assert ok.status_code == 204


@pytest.mark.asyncio
async def test_update_without_expected_revision_is_rejected(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id, _, channel = await _make_channel(client, auth_headers)
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{channel['id']}",
            json={"source_label": "x"},
            headers=auth_headers,
        )
        assert res.status_code == 422
