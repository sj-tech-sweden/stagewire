import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


async def _graph(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()


async def _legacy_universes(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/dmx-universes", headers=h)).json()


async def _setup(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "DMX"}, headers=h)).json()["id"]
    g = f"{BASE}/jobs/{job_id}/graph"
    a = (
        await client.post(f"{g}/fixtures", json={"purpose": "A", "footprint": 8}, headers=h)
    ).json()
    b = (
        await client.post(f"{g}/fixtures", json={"purpose": "B", "footprint": 8}, headers=h)
    ).json()
    desk = (
        await client.post(
            f"{g}/audio-devices", json={"name": "Lighting desk", "device_type": "other"}, headers=h
        )
    ).json()
    split = (
        await client.post(
            f"{g}/audio-devices", json={"name": "Splitter", "device_type": "other"}, headers=h
        )
    ).json()
    return job_id, g, a, b, desk, split


@pytest.mark.asyncio
async def test_a_universe_and_its_branching_chain_are_authored_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, a, b, desk, split = await _setup(client, h)

        uni = await client.post(
            f"{g}/universes",
            json={"name": "FOH rig", "source_device_id": desk["id"], "source_port": "DMX 1"},
            headers=h,
        )
        assert uni.status_code == 201, uni.text
        uni = uni.json()
        assert uni["kind"] == "dmx_universe" and uni["attributes"]["number"] == 1
        dup = await client.post(f"{g}/universes", json={"number": 1}, headers=h)
        assert dup.status_code == 409

        bad = await client.put(
            f"{g}/universes/{uni['id']}/chain",
            json={"steps": [{"device_id": a["id"], "parent_index": 0}]},
            headers=h,
        )
        assert bad.status_code == 422

        chain = await client.put(
            f"{g}/universes/{uni['id']}/chain",
            json={
                "steps": [
                    {"device_id": a["id"], "connector": "XLR5", "in_port": "In"},
                    {"device_id": b["id"], "parent_index": 0},
                    {"device_id": split["id"]},
                ]
            },
            headers=h,
        )
        assert chain.status_code == 200, chain.text
        edges = [e for e in chain.json()["edges"] if "step_id" in e["attributes"]]
        assert [e["attributes"]["position"] for e in edges] == [0, 1, 2]
        assert len(chain.json()["edges"]) == 4  # source -> universe plus three steps

        graph = await _graph(client, h, job_id)
        names = {d["id"]: d["name"] for d in graph["devices"]}
        path = {
            (names[e["src_device_id"]], names[e["dst_device_id"]])
            for e in graph["edges"]
            if e["signal"] == "dmx"
        }
        assert path == {
            ("Lighting desk", "FOH rig"),
            ("FOH rig", "A"),
            ("A", "B"),
            ("FOH rig", "Splitter"),
        }

        legacy = (await _legacy_universes(client, h, job_id))[0]
        assert (legacy["name"], legacy["source_port"], legacy["source_label"]) == (
            "FOH rig",
            "DMX 1",
            "Lighting desk",
        )
        tree = list(_walk(legacy["steps"]))
        assert [n["kind"] for n in tree] == ["fixture", "fixture", "device"]
        assert legacy["steps"][0]["children"][0]["id"] == tree[1]["id"]
        assert tree[0]["connector"] == "XLR5" and tree[0]["in_port"] == "In"


@pytest.mark.asyncio
async def test_universe_edits_and_deletes_write_through_to_the_legacy_rows(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, a, b, desk, split = await _setup(client, h)
        uni = (
            await client.post(f"{g}/universes", json={"source_device_id": desk["id"]}, headers=h)
        ).json()
        await client.put(
            f"{g}/universes/{uni['id']}/chain",
            json={"steps": [{"device_id": a["id"]}, {"device_id": b["id"], "parent_index": 0}]},
            headers=h,
        )

        node = {d["id"]: d for d in (await _graph(client, h, job_id))["devices"]}[uni["id"]]
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "name": "Stage left",
                "attributes": {**node["attributes"], "source_port": "Out 2"},
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await _legacy_universes(client, h, job_id))[0]
        assert (legacy["name"], legacy["source_port"]) == ("Stage left", "Out 2")

        # a step edge's connector reaches the step; removing it removes the step
        edges = [
            e for e in (await _graph(client, h, job_id))["edges"] if "step_id" in e["attributes"]
        ]
        first = next(e for e in edges if e["attributes"]["position"] == 0)
        res = await client.patch(
            f"{g}/edges/{first['id']}",
            json={"attributes": {"connector": "XLR3"}, "expected_revision": first["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert (
            list(_walk((await _legacy_universes(client, h, job_id))[0]["steps"]))[0]["connector"]
            == "XLR3"
        )
        last = next(
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if e["attributes"].get("position") == 1
        )
        assert (
            await client.delete(
                f"{g}/edges/{last['id']}", params={"expected_revision": last["revision"]}, headers=h
            )
        ).status_code == 204
        assert len(list(_walk((await _legacy_universes(client, h, job_id))[0]["steps"]))) == 1

        res = await client.put(
            f"{g}/universes/{uni['id']}/source", json={"device_id": None}, headers=h
        )
        assert res.status_code == 200
        assert (await _legacy_universes(client, h, job_id))[0]["source_device_id"] is None

        node = {d["id"]: d for d in (await _graph(client, h, job_id))["devices"]}[uni["id"]]
        assert (
            await client.delete(
                f"{g}/devices/{node['id']}",
                params={"expected_revision": node["revision"]},
                headers=h,
            )
        ).status_code == 204
        assert await _legacy_universes(client, h, job_id) == []
