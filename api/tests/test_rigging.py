from httpx import ASGITransport, AsyncClient

from app.domains.audio import router as audio_router
from app.domains.rigging.calc import WeightLoad, summarize_weights
from app.main import app

BASE = "/api/v1"


def test_weight_is_summed_per_point_and_flagged_over_capacity():
    points = [{"id": "p1", "name": "T1", "weight_capacity_kg": 10.0}]
    loads = [
        WeightLoad("Wash A", 6, "p1"),
        WeightLoad("Wash B", 6, "p1"),
        WeightLoad("Unpatched", 3, None),
    ]
    truss = summarize_weights(points, loads)[0]
    assert truss["load_kg"] == 12
    assert truss["percent"] == 120
    assert truss["over"] is True
    assert truss["loads"] == ["Wash A", "Wash B"]


async def test_the_power_tree_is_built_loads_are_plugged_and_checked(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Rig"}, headers=auth_headers)
        ).json()["id"]

        async def post(path, body, status=201):
            res = await client.post(f"{BASE}/jobs/{job_id}/{path}", json=body, headers=auth_headers)
            assert res.status_code == status, res.text
            return res.json()

        point = await post("rigging-points", {"name": "FOH truss", "weight_capacity_kg": 10})
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
                "outputs": [
                    {"connector": "schuko", "count": 4, "phase": "L1"},
                    {"connector": "powercon", "count": 4, "phase": "L2"},
                ],
            },
        )
        # A distro cannot hang from a connector its parent does not have.
        await post(
            "power-nodes",
            {
                "name": "Wrong",
                "kind": "breakout",
                "parent_id": source["id"],
                "feed_connector": "schuko",
            },
            status=422,
        )
        await client.post(
            f"{BASE}/jobs/{job_id}/devices",
            json={"name": "Robin R", "device_type": "fixture", "weight_kg": 6, "power_watts": 2000},
            headers=auth_headers,
        )
        fixture = await post(
            "fixtures", {"device_name": "Robin R", "universe": 1, "dmx_address": 1}
        )
        amp = await post(
            "devices", {"name": "Amp", "device_type": "amp", "weight_kg": 6, "power_watts": 2000}
        )
        element = await post(
            "plot-elements",
            {"element_type": "speaker_main", "label": "Main L", "linked_device_id": amp["id"]},
        )

        plugged = await client.patch(
            f"{BASE}/jobs/{job_id}/rigging/loads/fixture/{fixture['id']}",
            json={
                "rigging_point_id": point["id"],
                "power_node_id": distro["id"],
                "power_connector": "schuko",
            },
            headers=auth_headers,
        )
        assert plugged.status_code == 204, plugged.text
        plugged = await client.patch(
            f"{BASE}/jobs/{job_id}/rigging/loads/element/{element['id']}",
            json={
                "rigging_point_id": point["id"],
                "power_node_id": distro["id"],
                "power_connector": "powercon",
            },
            headers=auth_headers,
        )
        assert plugged.status_code == 204, plugged.text

        not_an_output = await client.patch(
            f"{BASE}/jobs/{job_id}/rigging/loads/fixture/{fixture['id']}",
            json={"power_connector": "cee16"},
            headers=auth_headers,
        )
        assert not_an_output.status_code == 422

        summary = (
            await client.get(f"{BASE}/jobs/{job_id}/rigging/summary", headers=auth_headers)
        ).json()
        truss = summary["points"][0]
        assert truss["load_kg"] == 12
        assert truss["over"] is True
        node = next(n for n in summary["nodes"] if n["id"] == distro["id"])
        assert node["amps"] == {"L1": 8.7, "L2": 8.7, "L3": 0.0}
        assert node["status"] == "ok"
        assert summary["errors"] == []
        loads = {row["label"]: row for row in summary["loads"]}
        assert loads["Robin R"]["power_status"] == "ok"

        busy = await client.delete(
            f"{BASE}/jobs/{job_id}/power-nodes/{distro['id']}", headers=auth_headers
        )
        assert busy.status_code == 409

        nodes = (await client.get(f"{BASE}/jobs/{job_id}/power-nodes", headers=auth_headers)).json()
        assert {n["name"] for n in nodes} == {"Mains", "Stage distro"}
        catalog = (await client.get(f"{BASE}/power-connectors", headers=auth_headers)).json()
        assert "powercon_true1" in {c["key"] for c in catalog}


async def test_switching_off_the_source_marks_its_loads_unpowered(auth_headers, monkeypatch):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Off"}, headers=auth_headers)
        ).json()["id"]
        source = (
            await client.post(
                f"{BASE}/jobs/{job_id}/power-nodes",
                json={
                    "name": "Mains",
                    "kind": "source",
                    "feed_connector": "cee16",
                    "outputs": [{"connector": "schuko", "count": 2}],
                },
                headers=auth_headers,
            )
        ).json()
        fixture = (
            await client.post(
                f"{BASE}/jobs/{job_id}/fixtures",
                json={"dmx_address": 1, "power_node_id": source["id"], "power_connector": "schuko"},
                headers=auth_headers,
            )
        ).json()
        assert fixture["power_node_id"] == source["id"]
        patched = await client.patch(
            f"{BASE}/jobs/{job_id}/power-nodes/{source['id']}",
            json={"active": False},
            headers=auth_headers,
        )
        assert patched.status_code == 200
        summary = (
            await client.get(f"{BASE}/jobs/{job_id}/rigging/summary", headers=auth_headers)
        ).json()
        assert summary["nodes"][0]["status"] == "unpowered"
        assert summary["loads"][0]["power_status"] == "unpowered"


async def test_venue_outlets_are_saved_on_the_venue_and_can_feed_a_source(
    auth_headers, monkeypatch
):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        venue = (
            await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=auth_headers)
        ).json()
        outlet = await client.post(
            f"{BASE}/venues/{venue['id']}/power-outlets",
            json={"name": "Wall FOH", "connector": "schuko", "x_cm": 300, "y_cm": 50},
            headers=auth_headers,
        )
        assert outlet.status_code == 201, outlet.text
        bad = await client.post(
            f"{BASE}/venues/{venue['id']}/power-outlets",
            json={"name": "Odd", "connector": "nema5"},
            headers=auth_headers,
        )
        assert bad.status_code == 422

        job = (
            await client.post(f"{BASE}/jobs", json={"title": "Outlets"}, headers=auth_headers)
        ).json()
        await client.put(
            f"{BASE}/jobs/{job['id']}/venue", json={"venue_id": venue["id"]}, headers=auth_headers
        )
        outlets = (
            await client.get(f"{BASE}/jobs/{job['id']}/power-outlets", headers=auth_headers)
        ).json()
        assert [o["name"] for o in outlets] == ["Wall FOH"]

        source = await client.post(
            f"{BASE}/jobs/{job['id']}/power-nodes",
            json={
                "name": "Wall FOH",
                "kind": "source",
                "feed_connector": "schuko",
                "venue_outlet_id": outlet.json()["id"],
                "outputs": [{"connector": "schuko", "count": 1}],
            },
            headers=auth_headers,
        )
        assert source.status_code == 201, source.text
        mismatch = await client.post(
            f"{BASE}/jobs/{job['id']}/power-nodes",
            json={
                "name": "Wrong feed",
                "kind": "source",
                "feed_connector": "cee16",
                "venue_outlet_id": outlet.json()["id"],
            },
            headers=auth_headers,
        )
        assert mismatch.status_code == 422


async def test_installation_wiring_needs_a_rating_and_nodes_can_stand_for_a_device(
    auth_headers, monkeypatch
):
    async def no_integration(db):
        return None

    monkeypatch.setattr(audio_router, "stockwire_product_fetcher", no_integration)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        job_id = (
            await client.post(f"{BASE}/jobs", json={"title": "Install"}, headers=auth_headers)
        ).json()["id"]
        unrated = await client.post(
            f"{BASE}/jobs/{job_id}/power-nodes",
            json={
                "name": "Venue feed",
                "kind": "source",
                "feed_connector": "install_3p",
                "outputs": [{"connector": "install_3p", "count": 1}],
            },
            headers=auth_headers,
        )
        assert unrated.status_code == 422
        assert "rating" in unrated.text
        device = (
            await client.post(
                f"{BASE}/jobs/{job_id}/devices",
                json={"name": "Stage DB", "device_type": "other"},
                headers=auth_headers,
            )
        ).json()
        rated = await client.post(
            f"{BASE}/jobs/{job_id}/power-nodes",
            json={
                "name": "Venue feed",
                "kind": "source",
                "feed_connector": "install_3p",
                "rating_amps": 32,
                "device_id": device["id"],
                "outputs": [{"connector": "install_3p", "count": 1}],
            },
            headers=auth_headers,
        )
        assert rated.status_code == 201, rated.text
        assert rated.json()["device_id"] == device["id"]
        summary = (
            await client.get(f"{BASE}/jobs/{job_id}/rigging/summary", headers=auth_headers)
        ).json()
        assert summary["nodes"][0]["rating_amps"] == 32
