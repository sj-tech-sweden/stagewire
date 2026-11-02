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
    """The universes as plain trees (what the old endpoint returned), read from the graph nodes."""
    graph = await _graph(client, h, job_id)
    names = {d["id"]: d for d in graph["devices"]}
    out = []
    for node in sorted(
        (d for d in graph["devices"] if d["kind"] == "dmx_universe"),
        key=lambda d: d["attributes"]["number"],
    ):
        steps = node["attributes"]["steps"]

        def tree(parent, steps=steps):
            return [
                {
                    "id": step["step_id"],
                    "kind": "fixture" if names[step["node_id"]]["kind"] == "fixture" else "device",
                    "label": names[step["node_id"]]["name"],
                    **{k: step[k] for k in ("in_port", "out_port", "connector", "notes")},
                    "children": tree(step["step_id"]),
                }
                for step in sorted(steps, key=lambda s: s["position"])
                if step["parent_id"] == parent
            ]

        source = node["attributes"].get("source_device_id")
        out.append(
            {
                "number": node["attributes"]["number"],
                "name": node["attributes"].get("name", ""),
                "source_port": node["attributes"].get("source_port", ""),
                "source_device_id": source,
                "source_label": names[source]["name"] if source else "",
                "steps": tree(None),
            }
        )
    return out


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


@pytest.mark.asyncio
async def test_renumbering_a_universe_into_a_taken_number_is_refused(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Numbers"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        first = (await client.post(f"{g}/universes", json={}, headers=h)).json()
        second = (await client.post(f"{g}/universes", json={}, headers=h)).json()
        assert (first["attributes"]["number"], second["attributes"]["number"]) == (1, 2)
        res = await client.patch(
            f"{g}/devices/{second['id']}",
            json={
                "attributes": {"number": 1},
                "expected_revision": second["revision"],
            },
            headers=h,
        )
        assert res.status_code == 409
        assert sorted(u["number"] for u in await _legacy_universes(client, h, job_id)) == [1, 2]
        free = await client.patch(
            f"{g}/devices/{second['id']}",
            json={"attributes": {"number": 7}, "expected_revision": second["revision"]},
            headers=h,
        )
        assert free.status_code == 200, free.text
        assert sorted(u["number"] for u in await _legacy_universes(client, h, job_id)) == [1, 7]


@pytest.mark.asyncio
async def test_deleting_a_step_edge_hands_its_children_to_its_parent(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, a, b, desk, split = await _setup(client, h)
        uni = (await client.post(f"{g}/universes", json={}, headers=h)).json()
        await client.put(
            f"{g}/universes/{uni['id']}/chain",
            json={
                "steps": [
                    {"device_id": split["id"]},
                    {"device_id": a["id"], "parent_index": 0},
                    {"device_id": b["id"], "parent_index": 1},
                ]
            },
            headers=h,
        )
        edges = (await _graph(client, h, job_id))["edges"]
        middle = next(e for e in edges if e["attributes"].get("position") == 1)
        res = await client.delete(
            f"{g}/edges/{middle['id']}", params={"expected_revision": middle["revision"]}, headers=h
        )
        assert res.status_code == 204
        tree = (await _legacy_universes(client, h, job_id))[0]["steps"]
        assert len(tree) == 1 and len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["children"] == []


@pytest.mark.asyncio
async def test_an_edit_on_a_device_without_fixtures_is_not_reported_as_saved(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, a, b, desk, split = await _setup(client, h)
        node = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["name"] == "Splitter"
        )
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={"attributes": {"location": "Truss 3"}, "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200
        legacy = next(
            d
            for d in (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()
            if d["name"] == "Splitter"
        )
        assert "location" not in legacy


@pytest.mark.asyncio
async def test_deleting_a_fixture_removes_its_step_and_moves_the_rest_up(auth_headers):
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
        node = {d["id"]: d for d in (await _graph(client, h, job_id))["devices"]}[a["id"]]
        res = await client.delete(
            f"{g}/devices/{a['id']}", params={"expected_revision": node["revision"]}, headers=h
        )
        assert res.status_code == 204, res.text
        tree = (await _legacy_universes(client, h, job_id))[0]["steps"]
        assert [(s["label"], s["children"]) for s in tree] == [("B", [])]
        # the universe still has its source edge and one chain edge
        edges = [e for e in (await _graph(client, h, job_id))["edges"] if e["signal"] == "dmx"]
        assert len(edges) == 2
