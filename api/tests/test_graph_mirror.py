import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _graph(client, headers, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=headers)).json()


@pytest.mark.asyncio
async def test_legacy_writes_appear_in_the_graph_and_are_broadcast(auth_headers, monkeypatch):
    sent: list[tuple[str, dict]] = []

    async def spy(job_id, event_type, payload):
        sent.append((event_type, payload))

    monkeypatch.setattr("app.domains.audio.ws.publish_job_event", spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Mirror"}, headers=h)).json()[
            "id"
        ]
        lst = (
            await client.post(
                f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH"}, headers=h
            )
        ).json()
        ch = (
            await client.post(
                f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels",
                json={"channel_number": 1, "source_label": "Kick", "phantom_power": True},
                headers=h,
            )
        ).json()

        graph = await _graph(client, h, job_id)
        names = {d["name"]: d for d in graph["devices"]}
        assert {"FOH", "Kick"} <= set(names)
        assert names["Kick"]["attributes"]["phantom_power"] is True
        assert any(t == "graph.device.upsert" for t, _ in sent)

        sent.clear()
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{ch['id']}",
            json={"source_label": "Kick In", "notes": "inside", "expected_revision": 1},
            headers=h,
        )
        assert res.status_code == 200
        names = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}
        assert names["Kick In"]["notes"] == "inside" and "Kick" not in names
        assert [p["name"] for t, p in sent if t == "graph.device.upsert"] == ["Kick In"]

        sent.clear()
        res = await client.delete(
            f"{BASE}/jobs/{job_id}/channels/{ch['id']}",
            params={"expected_revision": 2},
            headers=h,
        )
        assert res.status_code == 204
        assert "Kick In" not in {d["name"] for d in (await _graph(client, h, job_id))["devices"]}
        assert any(t == "graph.device.delete" for t, _ in sent)


@pytest.mark.asyncio
async def test_a_failed_legacy_write_does_not_touch_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Mirror 2"}, headers=h)).json()[
            "id"
        ]
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/channels/00000000-0000-0000-0000-000000000000",
            json={"source_label": "x", "expected_revision": 1},
            headers=h,
        )
        assert res.status_code == 404
        assert (await _graph(client, h, job_id))["devices"] == []
