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


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Round trip"}, headers=h)).json()[
        "id"
    ]
    lst = (
        await client.post(f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH"}, headers=h)
    ).json()
    box = (
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Stagebox", "device_type": "analog_stagebox"},
            headers=h,
        )
    ).json()
    ch = (
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels",
            json={"channel_number": 1, "source_label": "Kick"},
            headers=h,
        )
    ).json()
    point = await client.post(
        f"{BASE}/jobs/{job_id}/channels/{ch['id']}/patch-points",
        json={"position": 0, "point_type": "analog_stagebox", "device_id": box["id"]},
        headers=h,
    )
    assert point.status_code == 201, point.text
    return job_id, lst, box, ch, point.json()


async def _legacy_channel(client, h, job_id, list_id, channel_id):
    rows = (
        await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{list_id}/channels", headers=h)
    ).json()
    return next(r for r in rows if r["id"] == channel_id)


@pytest.mark.asyncio
async def test_graph_edits_write_through_to_the_legacy_rows(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, box, ch, point = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        devices = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}
        node = devices["Kick"]

        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "name": "Kick In",
                "notes": "inside the drum",
                "attributes": {
                    **node["attributes"],
                    "stand_type": "Short boom",
                    "phantom_power": True,
                },
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = await _legacy_channel(client, h, job_id, lst["id"], ch["id"])
        assert legacy["source_label"] == "Kick In"
        assert legacy["notes"] == "inside the drum"
        assert legacy["stand_type"] == "Short boom" and legacy["phantom_power"] is True
        assert legacy["revision"] > ch["revision"]

        # the channel is one node now, so a canvas edit is a revision of the channel too
        node = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Kick In"]
        await client.patch(
            f"{g}/devices/{node['id']}",
            json={"canvas_x_cm": 40, "expected_revision": node["revision"]},
            headers=h,
        )
        again = await _legacy_channel(client, h, job_id, lst["id"], ch["id"])
        assert again["revision"] > legacy["revision"]

        # and a later legacy edit of the same row flows back into the graph twin
        await client.patch(
            f"{BASE}/jobs/{job_id}/channels/{ch['id']}",
            json={"source_label": "Kick Out", "expected_revision": again["revision"]},
            headers=h,
        )
        node = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Kick Out"]
        assert node["canvas_x_cm"] == 40

        # device (stagebox) edits mirror too
        stagebox = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Stagebox"]
        await client.patch(
            f"{g}/devices/{stagebox['id']}",
            json={"name": "Stagebox SL", "expected_revision": stagebox["revision"]},
            headers=h,
        )
        devs = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
        assert [d["name"] for d in devs] == ["Stagebox SL"]


@pytest.mark.asyncio
async def test_graph_edge_edits_and_deletes_write_through(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, box, ch, point = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        edge = (await _graph(client, h, job_id))["edges"][0]

        res = await client.patch(
            f"{g}/edges/{edge['id']}",
            json={
                "attributes": {**edge["attributes"], "patch_label": "In 7", "connector": "XLR"},
                "cable_label": "A12",
                "expected_revision": edge["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = await _legacy_channel(client, h, job_id, lst["id"], ch["id"])
        assert legacy["patch_points"][0]["patch_label"] == "In 7"
        assert legacy["patch_points"][0]["connector"] == "XLR"
        kept = (await _graph(client, h, job_id))["edges"][0]
        assert kept["cable_label"] == "A12"  # graph-only field survives the sync

        res = await client.delete(
            f"{g}/edges/{kept['id']}", params={"expected_revision": kept["revision"]}, headers=h
        )
        assert res.status_code == 204
        legacy = await _legacy_channel(client, h, job_id, lst["id"], ch["id"])
        assert legacy["patch_points"] == []
        assert (await _graph(client, h, job_id))["edges"] == []


@pytest.mark.asyncio
async def test_graph_deletes_write_through_and_respect_in_use_devices(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, box, ch, point = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        devices = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}

        busy = await client.delete(
            f"{g}/devices/{devices['Stagebox']['id']}",
            params={"expected_revision": devices["Stagebox"]["revision"]},
            headers=h,
        )
        assert busy.status_code == 409
        assert len((await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()) == 1
        assert "Stagebox" in {d["name"] for d in (await _graph(client, h, job_id))["devices"]}

        gone = await client.delete(
            f"{g}/devices/{devices['Kick']['id']}",
            params={"expected_revision": devices["Kick"]["revision"]},
            headers=h,
        )
        assert gone.status_code == 204
        rows = (
            await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels", headers=h)
        ).json()
        assert rows == []

        free = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Stagebox"]
        assert (
            await client.delete(
                f"{g}/devices/{free['id']}",
                params={"expected_revision": free["revision"]},
                headers=h,
            )
        ).status_code == 204
        assert (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json() == []
