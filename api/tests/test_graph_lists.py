import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h):
    return (await client.post(f"{BASE}/jobs", json={"title": "Lists"}, headers=h)).json()["id"]


@pytest.mark.asyncio
async def test_a_channel_list_can_be_authored_entirely_through_the_graph_api(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        lst = await client.post(f"{g}/lists", json={"name": "FOH", "mixer_inputs": 32}, headers=h)
        assert lst.status_code == 201, lst.text
        assert lst.json()["kind"] == "channel_list"
        list_id = lst.json()["id"]

        first = await client.post(
            f"{g}/lists/{list_id}/channels", json={"source_label": "Kick"}, headers=h
        )
        assert first.status_code == 201, first.text
        assert first.json()["attributes"]["channel_number"] == 1
        batch = await client.post(
            f"{g}/lists/{list_id}/channels/batch",
            json=[{"source_label": "Snare"}, {"channel_number": 10, "source_label": "Vox"}],
            headers=h,
        )
        assert [c["attributes"]["channel_number"] for c in batch.json()] == [2, 10]

        # a catalog item with no legacy twin is made patchable on demand
        stagebox = (
            await client.post(
                f"{g}/devices",
                json={"domain": "audio", "name": "Stagebox", "stockwire_product_id": "12"},
                headers=h,
            )
        ).json()
        desk = (
            await client.post(f"{g}/devices", json={"domain": "audio", "name": "Desk"}, headers=h)
        ).json()
        chain = await client.put(
            f"{g}/channels/{first.json()['id']}/chain",
            json={
                "steps": [
                    {"device_id": stagebox["id"], "connector": "XLR", "patch_label": "In 3"},
                    {"device_id": desk["id"], "connector": "Dante"},
                ]
            },
            headers=h,
        )
        assert chain.status_code == 200, chain.text
        edges = chain.json()["edges"]
        assert [e["attributes"]["patch_label"] for e in edges] == ["In 3", ""]
        assert [e["attributes"]["position"] for e in edges] == [0, 1]

        out = await client.post(f"{g}/lists/{list_id}/outputs", json={"name": "Mon 1"}, headers=h)
        assert out.status_code == 201
        amp = (
            await client.post(f"{g}/devices", json={"domain": "audio", "name": "Amp"}, headers=h)
        ).json()
        bad = await client.put(
            f"{g}/outputs/{out.json()['id']}/chain",
            json={"steps": [{"device_id": desk["id"], "parent_index": 0}]},
            headers=h,
        )
        assert bad.status_code == 422
        ok = await client.put(
            f"{g}/outputs/{out.json()['id']}/chain",
            json={
                "steps": [
                    {"device_id": desk["id"]},
                    {"device_id": amp["id"], "connector": "XLR"},
                    {"device_id": stagebox["id"], "parent_index": 0},
                ]
            },
            headers=h,
        )
        assert ok.status_code == 200, ok.text
        assert len(ok.json()["edges"]) == 3  # console->bus plus two chain edges

        # the shadow rows exist, so the unmoved readers and the legacy editor see the same list
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()
        assert [c["source_label"] for c in legacy[0]["channels"]] == ["Kick", "Snare", "Vox"]
        assert len(legacy[0]["channels"][0]["patch_points"]) == 2
        assert [p["device_id"] is not None for p in legacy[0]["outputs"][0]["points"]] == [True] * 3
        devices = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
        assert {d["name"] for d in devices} == {"Stagebox", "Desk", "Amp"}

        csv = await client.get(
            f"{g}/lists/{list_id}/export", params={"plugin": "generic_csv"}, headers=h
        )
        assert csv.status_code == 200

        # replacing a chain replaces it
        again = await client.put(
            f"{g}/channels/{first.json()['id']}/chain",
            json={"steps": [{"device_id": desk["id"]}]},
            headers=h,
        )
        assert len(again.json()["edges"]) == 1
        sheets = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()
        assert len(sheets[0]["channels"][0]["patch_points"]) == 1


@pytest.mark.asyncio
async def test_list_endpoints_reject_the_wrong_kind_of_node(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        node = (
            await client.post(f"{g}/devices", json={"domain": "audio", "name": "Mic"}, headers=h)
        ).json()
        assert (
            await client.post(f"{g}/lists/{node['id']}/channels", json={}, headers=h)
        ).status_code == 404
        assert (
            await client.put(f"{g}/channels/{node['id']}/chain", json={"steps": []}, headers=h)
        ).status_code == 404


@pytest.mark.asyncio
async def test_patch_sheets_include_output_chains(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Sheets"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        lst = (await client.post(f"{g}/lists", json={"name": "FOH"}, headers=h)).json()
        out = (
            await client.post(f"{g}/lists/{lst['id']}/outputs", json={"name": "Main"}, headers=h)
        ).json()
        box = (
            await client.post(
                f"{g}/audio-devices", json={"name": "Amp", "device_type": "other"}, headers=h
            )
        ).json()
        res = await client.put(
            f"{g}/outputs/{out['id']}/chain", json={"steps": [{"device_id": box["id"]}]}, headers=h
        )
        assert res.status_code == 200, res.text
        sheets = await client.get(f"{BASE}/jobs/{job_id}/patch-sheets", headers=h)
        assert sheets.status_code == 200, sheets.text
        rows = [r for sheet in sheets.json() for r in sheet["channels"]]
        assert any(r["kind"] == "output" and r["point"]["revision"] >= 1 for r in rows)


@pytest.mark.asyncio
async def test_outputs_are_added_in_bulk(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Bulk out"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        lst = (await client.post(f"{g}/lists", json={"name": "FOH"}, headers=h)).json()
        res = await client.post(
            f"{g}/lists/{lst['id']}/outputs/batch",
            json=[{"name": f"Aux {n}", "mode": "mono"} for n in range(1, 7)],
            headers=h,
        )
        assert res.status_code == 201, res.text
        assert [n["name"] for n in res.json()] == [f"Aux {n}" for n in range(1, 7)]
        assert [n["position"] for n in res.json()] == list(range(6))
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()[0]
        assert [o["name"] for o in legacy["outputs"]] == [f"Aux {n}" for n in range(1, 7)]
        too_many = await client.post(
            f"{g}/lists/{lst['id']}/outputs/batch", json=[{"name": "x"}] * 201, headers=h
        )
        assert too_many.status_code == 422


@pytest.mark.asyncio
async def test_a_channel_without_a_label_exports_an_empty_label_not_its_fallback_name(auth_headers):
    import uuid

    from app.core import db as db_mod
    from app.domains.reports import registry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Blank"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        lst = (await client.post(f"{g}/lists", json={"name": "FOH"}, headers=h)).json()
        res = await client.post(f"{g}/lists/{lst['id']}/channels", json={}, headers=h)
        assert res.status_code == 201
        assert res.json()["name"].startswith("Ch ")
    async with db_mod.SessionLocal() as db:
        rows = (await registry._channel_list_context(db, uuid.UUID(job_id)))["channels"]
    assert [r["source_label"] for r in rows] == [""]


@pytest.mark.asyncio
async def test_a_channel_keeps_its_source_device_link_across_syncs(auth_headers):
    """`source_device_id` is a graph-only attribute: it must survive the legacy sync and edits."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        lst = (await client.post(f"{g}/lists", json={"name": "FOH"}, headers=h)).json()
        channel = (
            await client.post(
                f"{g}/lists/{lst['id']}/channels", json={"source_label": "Vox"}, headers=h
            )
        ).json()
        mic = (
            await client.post(
                f"{g}/audio-devices", json={"name": "SM58 #1", "device_type": "other"}, headers=h
            )
        ).json()

        patched = await client.patch(
            f"{g}/devices/{channel['id']}",
            json={
                "attributes": {"device": "SM58 #1", "source_device_id": mic["id"]},
                "expected_revision": channel["revision"],
            },
            headers=h,
        )
        assert patched.status_code == 200, patched.text

        # reading the graph runs the sync from the legacy rows, and a later edit of another
        # attribute merges instead of replacing the link
        graph = (await client.get(g, headers=h)).json()
        node = next(d for d in graph["devices"] if d["id"] == channel["id"])
        assert node["attributes"]["source_device_id"] == mic["id"]
        again = await client.patch(
            f"{g}/devices/{channel['id']}",
            json={"attributes": {"phantom_power": True}, "expected_revision": node["revision"]},
            headers=h,
        )
        assert again.json()["attributes"]["source_device_id"] == mic["id"]
        graph = (await client.get(g, headers=h)).json()
        node = next(d for d in graph["devices"] if d["id"] == channel["id"])
        assert node["attributes"]["source_device_id"] == mic["id"]
        assert node["attributes"]["phantom_power"] is True


@pytest.mark.asyncio
async def test_a_channel_has_no_connector_of_its_own(auth_headers):
    """The connector now belongs to the device port and to patch points; a channel-level one was
    redundant. It is dropped from the read model, the graph attributes, and the channel export,
    while a patch point keeps its connector."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        list_id = (await client.post(f"{g}/lists", json={"name": "FOH"}, headers=h)).json()["id"]
        res = await client.post(
            f"{g}/lists/{list_id}/channels",
            json={"source_label": "Kick", "connector": "XLR"},
            headers=h,
        )
        assert res.status_code == 201, res.text
        node = res.json()
        assert "connector" not in node["attributes"]
        devices = (await client.get(g, headers=h)).json()["devices"]
        stored = next(d for d in devices if d["id"] == node["id"])
        assert "connector" not in stored["attributes"]

        legacy = (await client.get(f"{BASE}/jobs/{job_id}/channel-lists", headers=h)).json()
        assert "connector" not in legacy[0]["channels"][0]

        csv = await client.get(
            f"{g}/lists/{list_id}/export", params={"plugin": "generic_csv"}, headers=h
        )
        assert csv.status_code == 200, csv.text
        with zipfile.ZipFile(io.BytesIO(csv.content)) as zf:
            name = next(n for n in zf.namelist() if n.endswith("_inputs.csv"))
            header = zf.read(name).decode().splitlines()[0]
        assert "connector" not in header.lower()
