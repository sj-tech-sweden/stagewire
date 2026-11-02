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


@pytest.mark.asyncio
async def test_power_edge_edits_write_through_and_are_not_reverted_by_the_next_sync(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        edge = next(
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if e["dst_device_id"] == distro["id"]
        )
        res = await client.patch(
            f"{g}/edges/{edge['id']}",
            json={"phase": "L2", "expected_revision": edge["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        assert next(n for n in nodes if n["kind"] == "distro")["phase"] == "L2"
        await client.post(f"{g}/backfill", headers=h)
        again = next(
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if e["dst_device_id"] == distro["id"]
        )
        assert again["phase"] == "L2"

        wrong = await client.patch(
            f"{g}/edges/{again['id']}",
            json={"attributes": {"connector": "schuko"}, "expected_revision": again["revision"]},
            headers=h,
        )
        assert wrong.status_code == 422


@pytest.mark.asyncio
async def test_a_device_backed_power_node_and_shared_device_loads_are_edited_by_their_own_rows(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        gear = await post("audio-devices", {"name": "Rack distro", "device_type": "other"})
        backed = await post(
            "power-nodes",
            {
                "name": "Rack",
                "kind": "distro",
                "parent_id": source["id"],
                "feed_connector": "cee32_3p",
                "device_id": gear["id"],
                "outputs": [{"connector": "schuko", "count": 2}],
            },
        )
        assert backed["id"] == gear["id"]
        node = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["id"] == gear["id"]
        )
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={"attributes": {"rating_amps": 16}, "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        assert next(n for n in nodes if n["name"] == "Rack")["rating_amps"] == 16

        chain_bad = await client.put(
            f"{g}/video-inputs/{source['id']}/chain", json={"steps": []}, headers=h
        )
        assert chain_bad.status_code == 404


@pytest.mark.asyncio
async def test_a_power_or_rigging_node_cannot_be_used_as_a_chain_device(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        point = await post("rigging-points", {"name": "T"})
        vlist = (await client.post(f"{g}/video-lists", json={}, headers=h)).json()
        vin = (
            await client.post(f"{g}/video-lists/{vlist['id']}/inputs", json={}, headers=h)
        ).json()
        for node in (source, point):
            res = await client.put(
                f"{g}/video-inputs/{vin['id']}/chain",
                json={"steps": [{"device_id": node["id"]}]},
                headers=h,
            )
            assert res.status_code == 422, res.text
        refs = {d["legacy_ref"] for d in (await _graph(client, h, job_id))["devices"]}
        assert point["legacy_ref"] in refs and source["legacy_ref"] in refs


@pytest.mark.asyncio
async def test_a_projector_in_an_input_chain_leaves_no_new_devices_behind(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        vlist = (await client.post(f"{g}/video-lists", json={}, headers=h)).json()
        vin = (
            await client.post(f"{g}/video-lists/{vlist['id']}/inputs", json={}, headers=h)
        ).json()
        proj = await post("audio-devices", {"name": "Proj", "device_type": "projector"})
        before = len((await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json())
        res = await client.put(
            f"{g}/video-inputs/{vin['id']}/chain",
            json={"steps": [{"device_id": proj["id"]}]},
            headers=h,
        )
        assert res.status_code == 422
        assert len((await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()) == before


@pytest.mark.asyncio
async def test_loads_of_fixtures_on_the_same_device_are_assigned_one_by_one(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Robin", "device_type": "fixture"},
            headers=h,
        )
        for address in (1, 20):
            await post("fixtures", {"device_name": "Robin", "universe": 1, "dmx_address": address})
        point = await post("rigging-points", {"name": "T"})
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        loads = summary["loads"]
        assert len(loads) == 2 and len({(row["kind"], row["load_id"]) for row in loads}) == 2
        first = loads[0]
        res = await client.put(
            f"{g}/loads/{first['id']}",
            json={"load_id": first["load_id"], "rigging_point_id": point["id"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        fixtures = {
            f["id"]: f
            for f in (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()
        }
        assert fixtures[first["load_id"]]["rigging_point_id"] is not None
        other = next(row for row in loads if row["load_id"] != first["load_id"])
        assert fixtures[other["load_id"]]["rigging_point_id"] is None


@pytest.mark.asyncio
async def test_extension_cords_breakouts_edits_and_plain_devices_on_the_power_tree(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        breakout = await post(
            "power-nodes",
            {
                "name": "Breakout",
                "kind": "breakout",
                "parent_id": distro["id"],
                "feed_connector": "schuko",
                "outputs": [{"connector": "schuko", "count": 3}],
            },
        )

        cord = await post(
            f"power-nodes/{distro['id']}/extension", {"length_m": 10, "name": "10 m skarv"}
        )
        assert cord["kind"] == "extension" and cord["attributes"]["length_m"] == 10
        nodes = {
            n["name"]: n
            for n in (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        }
        assert nodes["Stage distro"]["parent_id"] == nodes["10 m skarv"]["id"]
        assert nodes["10 m skarv"]["parent_id"] == nodes["Mains"]["id"]
        await client.post(f"{g}/backfill", headers=h)
        again = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["id"] == cord["id"]
        )
        assert again["attributes"]["length_m"] == 10

        refused = await post(f"power-nodes/{source['id']}/extension", {"length_m": 5}, status=422)
        assert refused

        # a breakout is edited after creation: renamed, re-typed and moved
        node = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["id"] == breakout["id"]
        )
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "name": "Breakout FOH",
                "notes": "behind the riser",
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = next(
            n
            for n in (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
            if n["id"] == breakout["attributes"]["power_id"]
        )
        assert (legacy["name"], legacy["notes"]) == ("Breakout FOH", "behind the riser")

        bad_move = await client.put(
            f"{g}/power-nodes/{breakout['id']}/parent",
            json={"parent_id": cord["id"], "feed_connector": "schuko"},
            headers=h,
        )
        assert bad_move.status_code == 422
        moved = await client.put(
            f"{g}/power-nodes/{breakout['id']}/parent",
            json={"parent_id": cord["id"], "feed_connector": "cee32_3p"},
            headers=h,
        )
        assert moved.status_code == 200, moved.text
        nodes = {
            n["id"]: n
            for n in (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        }
        assert (
            nodes[breakout["attributes"]["power_id"]]["parent_id"] == cord["attributes"]["power_id"]
        )

        # a plain device is plugged into a node with its power inlet recorded
        gear = await post(
            "audio-devices", {"name": "Amp", "device_type": "other", "power_watts": 800}
        )
        node = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["id"] == gear["id"]
        )
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={"attributes": {"power_inlet": "iec_c13"}, "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        plugged = await client.put(
            f"{g}/loads/{gear['id']}",
            json={"power_node_id": breakout["id"], "power_connector": "schuko"},
            headers=h,
        )
        assert plugged.status_code == 200, plugged.text
        assert plugged.json()["attributes"]["power_inlet"] == "iec_c13"
        assert plugged.json()["attributes"]["power_node_id"] == breakout["id"]
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        load = next(row for row in summary["loads"] if row["kind"] == "device")
        assert load["id"] == gear["id"] and load["power_node_id"] == breakout["id"]
        feed = next(
            e
            for e in (await _graph(client, h, job_id))["edges"]
            if e["dst_device_id"] == gear["id"] and e["signal"] == "power"
        )
        res = await client.delete(
            f"{g}/edges/{feed['id']}", params={"expected_revision": feed["revision"]}, headers=h
        )
        assert res.status_code == 204, res.text
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert next(r for r in summary["loads"] if r["kind"] == "device")["power_node_id"] is None


@pytest.mark.asyncio
async def test_the_power_sheet_lists_inlets_cables_and_extension_cords(auth_headers):
    from app.core import db as db_mod
    from app.domains.reports.power_context import cable_for, cord_for, power_sheet_context

    assert [cord_for(x) for x in (1, 5.1, 12, 60)] == [2, 10, 15, 60]
    assert cable_for("", "schuko") == "IEC C13 → Schuko 16 A"
    assert cable_for("attached_schuko", "schuko") == "Fixed cable (Schuko)"
    assert cable_for("powercon", "powercon") == "powerCON → powerCON 20 A"
    assert cable_for("none", "schuko") == ""

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        breakout = await post(
            "power-nodes",
            {
                "name": "Breakout",
                "kind": "breakout",
                "parent_id": distro["id"],
                "feed_connector": "schuko",
                "outputs": [{"connector": "schuko", "count": 4}],
            },
        )
        await post(f"power-nodes/{breakout['id']}/extension", {"length_m": 10, "name": "Skarv 10"})
        amp = await post(
            "audio-devices", {"name": "Amp", "device_type": "other", "power_watts": 800}
        )
        rack = await post(
            "audio-devices",
            {
                "name": "Rack",
                "device_type": "other",
                "power_watts": 200,
                "power_inlet": "attached_schuko",
            },
        )
        await post("audio-devices", {"name": "Loose", "device_type": "other", "power_watts": 50})
        await post(
            "audio-devices",
            {"name": "Mic", "device_type": "other", "power_watts": 5, "power_inlet": "none"},
        )
        for gear in (amp, rack):
            res = await client.put(
                f"{g}/loads/{gear['id']}",
                json={"power_node_id": breakout["id"], "power_connector": "schuko"},
                headers=h,
            )
            assert res.status_code == 200, res.text

    async with db_mod.SessionLocal() as db:
        ctx = await power_sheet_context(db, __import__("uuid").UUID(job_id))
    loads = {row["device"]: row for row in ctx["power_loads"]}
    assert loads["Amp"]["cable"] == "IEC C13 → Schuko 16 A" and loads["Amp"]["inlet"] == "IEC C13"
    assert loads["Rack"]["cable"] == "Fixed cable (Schuko)"
    assert loads["Loose"]["cable"] == "Not plugged in"
    assert "Mic" not in loads
    assert ctx["power_cords"][0]["name"] == "Skarv 10" and ctx["power_cords"][0]["length_m"] == 10
    assert (
        ctx["power_cords"][0]["from"] == "Stage distro"
        and ctx["power_cords"][0]["to"] == "Breakout"
    )
    packed = {row["cable"]: row["count"] for row in ctx["power_cables"]}
    assert packed == {
        "IEC C13 → Schuko 16 A": 1,
        "Fixed cable (Schuko)": 1,
        "Extension cord 10 m": 1,
    }
    kinds = {row["name"]: row["kind"] for row in ctx["power_tree"]}
    assert kinds["Skarv 10"] == "extension"


@pytest.mark.asyncio
async def test_a_nodes_feed_can_be_cut_and_a_plugged_device_unplugged(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        res = await client.put(
            f"{g}/power-nodes/{distro['id']}/parent", json={"parent_id": None}, headers=h
        )
        assert res.status_code == 200, res.text
        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=h)).json()
        cut = next(n for n in nodes if n["name"] == "Stage distro")
        assert cut["parent_id"] is None and cut["feed_connector"] == ""
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert (
            next(n for n in summary["nodes"] if n["name"] == "Stage distro")["status"]
            == "unpowered"
        )
        edges = [e for e in (await _graph(client, h, job_id))["edges"] if e["signal"] == "power"]
        assert edges == []

        gear = await post(
            "audio-devices", {"name": "Amp", "device_type": "other", "power_watts": 100}
        )
        res = await client.put(
            f"{g}/loads/{gear['id']}",
            json={"power_node_id": source["id"], "power_connector": "cee32_3p"},
            headers=h,
        )
        assert res.status_code == 200, res.text
        res = await client.put(f"{g}/loads/{gear['id']}", json={"power_node_id": None}, headers=h)
        assert res.status_code == 200, res.text
        assert res.json()["attributes"].get("power_node_id") is None


@pytest.mark.asyncio
async def test_the_power_sheet_gives_each_cable_a_standard_length_from_the_plot(auth_headers):
    import uuid

    from app.core import db as db_mod
    from app.domains.reports.power_context import power_sheet_context

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id, g, post, source, distro = await _tree(client, h)
        breakout = await post(
            "power-nodes",
            {
                "name": "Breakout",
                "kind": "breakout",
                "parent_id": distro["id"],
                "feed_connector": "schuko",
                "outputs": [{"connector": "schuko", "count": 4}],
            },
        )
        legacy_id = breakout["attributes"]["power_id"]
        res = await client.patch(
            f"{BASE}/jobs/{job_id}/power-nodes/{legacy_id}", json={"x_cm": 0, "y_cm": 0}, headers=h
        )
        assert res.status_code == 200, res.text
        gear = await post(
            "audio-devices", {"name": "Amp", "device_type": "other", "power_watts": 400}
        )
        node = next(
            d for d in (await _graph(client, h, job_id))["devices"] if d["id"] == gear["id"]
        )
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={"canvas_x_cm": 600, "canvas_y_cm": 0, "expected_revision": node["revision"]},
            headers=h,
        )
        assert res.status_code == 200, res.text
        await client.put(
            f"{g}/loads/{gear['id']}",
            json={"power_node_id": breakout["id"], "power_connector": "schuko"},
            headers=h,
        )

    async with db_mod.SessionLocal() as db:
        ctx = await power_sheet_context(db, uuid.UUID(job_id))
    amp = next(row for row in ctx["power_loads"] if row["device"] == "Amp")
    # 6 m + 10 % + 1 m slack = 7.6 m, which is packed as a 10 m cable
    assert amp["length_m"] == 10
    assert {row["cable"]: row["count"] for row in ctx["power_cables"]} == {
        "IEC C13 → Schuko 16 A 10 m": 1
    }
