import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.main import app

BASE = "/api/v1"


async def _graph(client, h, job_id):
    return (await client.get(f"{BASE}/jobs/{job_id}/graph", headers=h)).json()


@pytest.fixture(autouse=True)
def _no_stockwire(monkeypatch):
    async def none(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", none)


async def _tree(client, h):
    job_id = (await client.post(f"{BASE}/jobs", json={"title": "Rig"}, headers=h)).json()["id"]
    g = f"{BASE}/jobs/{job_id}/graph"

    async def post(path, body, status=201):
        res = await client.post(f"{g}/{path}", json=body, headers=h)
        assert res.status_code == status, res.text
        return res.json()

    source = await post(
        "power-nodes",
        {
            "name": "Mains",
            "kind": "source",
            "feed_connector": "cee63_3p",
            "rating_amps": 63,
            "outputs": [{"connector": "cee32_3p", "count": 2}],
        },
    )
    distro = await post(
        "power-nodes",
        {
            "name": "Stage distro",
            "kind": "distro",
            "parent_id": source["id"],
            "feed_connector": "cee32_3p",
            "outputs": [{"connector": "schuko", "count": 4, "phase": "L1"}],
        },
    )
    return job_id, g, post, source, distro


@pytest.mark.asyncio
async def test_rigging_points_and_the_power_tree_are_authored_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        assert source["domain"] == "power" and source["kind"] == "source"
        assert distro["kind"] == "distro"

        wrong = await post(
            "power-nodes",
            {
                "name": "Wrong",
                "kind": "breakout",
                "parent_id": source["id"],
                "feed_connector": "schuko",
            },
            status=422,
        )
        assert "output" in str(wrong).lower()
        bad_parent = await post(
            "power-nodes",
            {"kind": "distro", "parent_id": "00000000-0000-0000-0000-000000000000"},
            422,
        )
        assert bad_parent

        point = await post("rigging-points", {"name": "FOH truss", "weight_capacity_kg": 10})
        assert point["kind"] == "rigging_point" and point["domain"] == "rigging"
        assert point["attributes"]["weight_capacity_kg"] == 10

        edges = [e for e in (await _graph(client, h, job_id))["edges"] if e["signal"] == "power"]
        assert [(e["src_device_id"], e["dst_device_id"]) for e in edges] == [
            (source["id"], distro["id"])
        ]


@pytest.mark.asyncio
async def test_rigging_and_power_edits_write_through_and_loads_are_assigned(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        point = await post("rigging-points", {"name": "FOH truss", "weight_capacity_kg": 10})
        fixture = await post("fixtures", {"purpose": "Wash", "footprint": 8})

        res = await client.patch(
            f"{g}/devices/{point['id']}",
            json={
                "name": "Upstage truss",
                "attributes": {"weight_capacity_kg": 500},
                "expected_revision": point["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/rigging-points", headers=h)).json()[0]
        assert (legacy["name"], legacy["weight_capacity_kg"]) == ("Upstage truss", 500)

        res = await client.patch(
            f"{g}/devices/{distro['id']}",
            json={
                "name": "Main distro",
                "attributes": {"rating_amps": 32},
                "expected_revision": distro["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        row = next(n for n in nodes if n["kind"] == "distro")
        assert (row["name"], row["rating_amps"]) == ("Main distro", 32)

        res = await client.put(
            f"{g}/loads/{fixture['id']}",
            json={
                "rigging_point_id": point["id"],
                "power_node_id": distro["id"],
                "power_connector": "schuko",
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        assert res.json()["attributes"]["rigging_point_id"] == point["id"]
        assert res.json()["attributes"]["power_node_id"] == distro["id"]
        legacy_fx = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()[0]
        assert legacy_fx["power_connector"] == "schuko"
        assert legacy_fx["rigging_point_id"] is not None

        refused = await client.put(
            f"{g}/loads/{fixture['id']}", json={"power_connector": "cee16"}, headers=h
        )
        assert refused.status_code == 422

        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert summary["points"][0]["id"] == point["id"]
        assert summary["nodes"][0]["id"] in (source["id"], distro["id"])
        load = summary["loads"][0]
        assert load["id"] == fixture["id"] and load["power_node_id"] == distro["id"]
        assert load["rigging_point_id"] == point["id"] and load["kind"] == "fixture"

        graph = await _graph(client, h, job_id)
        feed = next(
            e
            for e in graph["edges"]
            if e["dst_device_id"] == fixture["id"] and e["signal"] == "power"
        )
        res = await client.delete(
            f"{g}/edges/{feed['id']}", params={"expected_revision": feed["revision"]}, headers=h
        )
        assert res.status_code == 204, res.text
        legacy_fx = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()[0]
        assert legacy_fx["power_node_id"] is None

        own = next(
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if e["dst_device_id"] == distro["id"]
        )
        res = await client.delete(
            f"{g}/edges/{own['id']}", params={"expected_revision": own["revision"]}, headers=h
        )
        assert res.status_code == 409


@pytest.mark.asyncio
async def test_power_nodes_with_feeds_or_loads_cannot_be_deleted_and_points_can(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        point = await post("rigging-points", {"name": "T"})

        nodes = {d["id"]: d for d in (await _graph(client, h, job_id))["devices"]}
        res = await client.delete(
            f"{g}/devices/{source['id']}",
            params={"expected_revision": nodes[source["id"]]["revision"]},
            headers=h,
        )
        assert res.status_code == 409
        assert len((await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()) == 2

        res = await client.delete(
            f"{g}/devices/{distro['id']}",
            params={"expected_revision": nodes[distro["id"]]["revision"]},
            headers=h,
        )
        assert res.status_code == 204, res.text
        res = await client.delete(
            f"{g}/devices/{point['id']}",
            params={"expected_revision": nodes[point["id"]]["revision"]},
            headers=h,
        )
        assert res.status_code == 204
        assert (await client.get(f"{BASE}/jobs/{job_id}/rigging-points", headers=h)).json() == []


@pytest.mark.asyncio
async def test_an_extra_feed_is_added_through_the_graph_and_removed_by_its_edge(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        second = await post(
            "power-nodes",
            {
                "name": "Mains B",
                "kind": "source",
                "feed_connector": "cee63_3p",
                "rating_amps": 63,
                "outputs": [{"connector": "cee32_3p", "count": 1}],
            },
        )
        res = await client.post(
            f"{g}/power-nodes/{distro['id']}/feeds",
            json={"parent_id": second["id"], "feed_connector": "cee32_3p"},
            headers=h,
        )
        assert res.status_code == 201, res.text
        edges = [
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if e["signal"] == "power" and e["dst_device_id"] == distro["id"]
        ]
        assert len(edges) == 2
        extra = next(e for e in edges if e["src_device_id"] == second["id"])
        res = await client.delete(
            f"{g}/edges/{extra['id']}", params={"expected_revision": extra["revision"]}, headers=h
        )
        assert res.status_code == 204, res.text
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        assert next(n for n in nodes if n["kind"] == "distro")["feeds"] == []
