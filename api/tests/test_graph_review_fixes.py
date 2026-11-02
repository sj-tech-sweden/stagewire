import asyncio
from uuid import UUID

import pytest
from audio_seed import seed_device
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph.mirror import sync_job_to_graph
from app.main import app

BASE = "/api/v1"


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Fixes"}, headers=h)).json()["id"]
    lst = (
        await client.post(f"{BASE}/jobs/{job_id}/channel-lists", json={"name": "FOH"}, headers=h)
    ).json()
    ch = (
        await client.post(
            f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels",
            json={"channel_number": 1, "source_label": "Kick"},
            headers=h,
        )
    ).json()
    box = (
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Stagebox", "device_type": "analog_stagebox"},
            headers=h,
        )
    ).json()
    await client.post(
        f"{BASE}/jobs/{job_id}/channels/{ch['id']}/patch-points",
        json={"position": 0, "point_type": "analog_stagebox", "device_id": box["id"]},
        headers=h,
    )
    return job_id, lst, ch, box


async def _graph(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()


@pytest.mark.asyncio
async def test_a_legacy_delete_removes_graph_rows_even_after_graph_edits(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, ch, box = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        graph = await _graph(client, h, job_id)
        kick = next(d for d in graph["devices"] if d["name"] == "Kick")
        edge = graph["edges"][0]
        await client.patch(
            f"{g}/devices/{kick['id']}",
            json={"canvas_x_cm": 5, "name": "Kick (graph)", "expected_revision": kick["revision"]},
            headers=h,
        )
        await client.patch(
            f"{g}/edges/{edge['id']}",
            json={"cable_label": "A1", "phase": None, "expected_revision": edge["revision"]},
            headers=h,
        )
        rows = (
            await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels", headers=h)
        ).json()
        res = await client.delete(
            f"{BASE}/jobs/{job_id}/channels/{ch['id']}",
            params={"expected_revision": rows[0]["revision"]},
            headers=h,
        )
        assert res.status_code == 204, res.text
        after = await _graph(client, h, job_id)
        assert "Kick (graph)" not in {d["name"] for d in after["devices"]}
        assert after["edges"] == []


@pytest.mark.asyncio
async def test_a_canvas_move_does_not_freeze_a_node_against_legacy_edits(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, ch, box = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        stagebox = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["name"] == "Stagebox"
        )
        moved = await client.patch(
            f"{g}/devices/{stagebox['id']}",
            json={"canvas_x_cm": 10, "expected_revision": stagebox["revision"]},
            headers=h,
        )
        assert moved.json()["graph_edited"] is False
        await client.patch(
            f"{BASE}/jobs/{job_id}/devices/{box['id']}", json={"name": "Stagebox SL"}, headers=h
        )
        names = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}
        assert names["Stagebox SL"]["canvas_x_cm"] == 10


@pytest.mark.asyncio
async def test_a_graph_device_keeps_its_kind_and_ports_when_it_gets_a_legacy_twin(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, ch, box = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        graph = await _graph(client, h, job_id)
        kick = next(d for d in graph["devices"] if d["name"] == "Kick")
        desk = (
            await client.post(
                f"{g}/devices",
                json={
                    "domain": "audio",
                    "kind": "mixer",
                    "name": "Desk",
                    "ports": [
                        {"id": "in-dante", "direction": "in", "connector": "dante", "channels": 64}
                    ],
                },
                headers=h,
            )
        ).json()
        res = await client.put(
            f"{g}/channels/{kick['id']}/chain",
            json={"steps": [{"device_id": desk["id"]}]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        after = {d["name"]: d for d in (await _graph(client, h, job_id))["devices"]}["Desk"]
        assert after["kind"] == "mixer"
        assert any(p["connector"] == "dante" and p["channels"] == 64 for p in after["ports"])
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
        assert next(d for d in legacy if d["name"] == "Desk")["device_type"] == "mixer"


@pytest.mark.asyncio
async def test_patching_some_attributes_keeps_the_ones_that_tie_a_row_to_its_legacy_twin(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, ch, box = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        graph = await _graph(client, h, job_id)
        edge = graph["edges"][0]
        res = await client.patch(
            f"{g}/edges/{edge['id']}",
            json={"attributes": {"connector": "xlr3"}, "expected_revision": edge["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert res.json()["attributes"]["legacy_ref"] == edge["attributes"]["legacy_ref"]
        assert res.json()["attributes"]["chain"] == edge["attributes"]["chain"]
        again = await _graph(client, h, job_id)
        assert len(again["edges"]) == 1

        # the channel node owns its points, so the edge edit above moved its revision
        kick = next(d for d in again["devices"] if d["name"] == "Kick")
        res = await client.patch(
            f"{g}/devices/{kick['id']}",
            json={
                "attributes": {"stand_type": "Short boom"},
                "expected_revision": kick["revision"],
            },
            headers=h,
        )
        assert res.json()["attributes"]["list_id"] == kick["attributes"]["list_id"]
        assert res.json()["attributes"]["channel_number"] == 1


@pytest.mark.asyncio
async def test_overlapping_syncs_do_not_create_duplicate_nodes(auth_headers):
    async with db_mod.SessionLocal() as db:
        job = ProductionJob(title="Race")
        db.add(job)
        await db.flush()
        await seed_device(db, job.id, name="Kick", device_type="other")
        await seed_device(db, job.id, name="FOH", device_type="mixer")
        await db.commit()
        job_id = job.id
    await asyncio.gather(*[sync_job_to_graph(UUID(str(job_id))) for _ in range(6)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        graph = await _graph(client, auth_headers, job_id)
        names = [d["name"] for d in graph["devices"]]
        assert names.count("Kick") == 1 and names.count("FOH") == 1


@pytest.mark.asyncio
async def test_a_stale_graph_edit_leaves_the_legacy_row_alone(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, lst, ch, box = await _setup(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        kick = next(d for d in (await _graph(client, h, job_id))["devices"] if d["name"] == "Kick")
        await client.patch(
            f"{g}/devices/{kick['id']}",
            json={"name": "Kick A", "expected_revision": kick["revision"]},
            headers=h,
        )
        stale = await client.patch(
            f"{g}/devices/{kick['id']}",
            json={"name": "Kick B", "expected_revision": kick["revision"]},
            headers=h,
        )
        assert stale.status_code == 409
        rows = (
            await client.get(f"{BASE}/jobs/{job_id}/channel-lists/{lst['id']}/channels", headers=h)
        ).json()
        assert rows[0]["source_label"] == "Kick A"


@pytest.mark.asyncio
async def test_batch_created_plot_elements_get_their_legacy_row(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Batch"}, headers=h)).json()[
            "id"
        ]
        res = await client.post(
            f"{BASE}/jobs/{job_id}/graph/devices/batch",
            json=[
                {
                    "domain": "other",
                    "kind": "plot_element",
                    "name": "Riser",
                    "attributes": {"element_type": "riser"},
                },
                {
                    "domain": "other",
                    "kind": "plot_element",
                    "name": "Stage",
                    "attributes": {"element_type": "stage"},
                },
            ],
            headers=h,
        )
        assert res.status_code == 201, res.text
        elements = (await client.get(f"{BASE}/jobs/{job_id}/plot-elements", headers=h)).json()
        assert {e["label"] for e in elements} == {"Riser", "Stage"}
