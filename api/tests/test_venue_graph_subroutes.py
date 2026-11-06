"""Venue-scoped graph sub-route tests.

The venue "Standard Base Rig" editors reuse the job graph routes under the
``/venues/{venue_id}/graph`` prefix. These tests pin down that the venue variants
of the list / video / lighting / power / dmx / validation routes behave like their
job counterparts but are scoped to the venue (no job, no legacy mirror, no publish).
"""

from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _make_venue(client, headers):
    body = {
        "name": "Subroute Venue",
        "venue_width_cm": 1000,
        "venue_height_cm": 800,
    }
    resp = await client.post(f"{BASE}/venues", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_venue_create_fixture(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        # A venue needs its own fixture-type library (no shared built-in types).
        ftype = await client.post(
            f"{BASE}/venues/{venue_id}/fixture-types",
            json={"name": "LED wash", "footprint": 16},
            headers=auth_headers,
        )
        assert ftype.status_code == 201, ftype.text

        fixture = await client.post(
            f"{BASE}/venues/{venue_id}/graph/fixtures",
            json={"device_name": "Wash 1", "fixture_type": "LED wash", "footprint": 16},
            headers=auth_headers,
        )
        assert fixture.status_code == 201, fixture.text
        body = fixture.json()
        assert body["domain"] == "lighting" and body["kind"] == "fixture"
        assert body["attributes"].get("universe") == 1


async def test_venue_create_universe_and_set_source(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        universe = await client.post(
            f"{BASE}/venues/{venue_id}/graph/universes",
            json={"name": "House", "number": 1},
            headers=auth_headers,
        )
        assert universe.status_code == 201, universe.text
        universe_id = universe.json()["id"]
        assert universe.json()["kind"] == "dmx_universe"

        # A source device for the universe: a plain gear node in the venue.
        device = await client.post(
            f"{BASE}/venues/{venue_id}/graph/devices",
            json={
                "domain": "lighting",
                "kind": "other",
                "name": "Console",
                "expected_revision": 1,
            },
            headers=auth_headers,
        )
        assert device.status_code == 201, device.text
        device_id = device.json()["id"]

        source = await client.put(
            f"{BASE}/venues/{venue_id}/graph/universes/{universe_id}/source",
            json={"device_id": device_id, "port": "dmx_out"},
            headers=auth_headers,
        )
        assert source.status_code == 200, source.text
        assert source.json()["attributes"]["source_device_id"] == device_id


async def test_venue_create_video_list_and_rows(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        vlist = await client.post(
            f"{BASE}/venues/{venue_id}/graph/video-lists",
            json={"name": "Camera inputs"},
            headers=auth_headers,
        )
        assert vlist.status_code == 201, vlist.text
        list_id = vlist.json()["id"]
        assert vlist.json()["kind"] == "video_list"

        inputs = await client.post(
            f"{BASE}/venues/{venue_id}/graph/video-lists/{list_id}/inputs/batch",
            json=[
                {"source_label": "Cam 1", "input_number": 1},
                {"source_label": "Cam 2", "input_number": 2},
            ],
            headers=auth_headers,
        )
        assert inputs.status_code == 201, inputs.text
        assert len(inputs.json()) == 2
        assert all(r["kind"] == "video_input" for r in inputs.json())


async def test_venue_create_channel_list_and_channels(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        clist = await client.post(
            f"{BASE}/venues/{venue_id}/graph/lists",
            json={"name": "Input List"},
            headers=auth_headers,
        )
        assert clist.status_code == 201, clist.text
        list_id = clist.json()["id"]
        assert clist.json()["kind"] == "channel_list"

        channels = await client.post(
            f"{BASE}/venues/{venue_id}/graph/lists/{list_id}/channels/batch",
            json=[
                {"source_label": "Vox", "channel_number": 1},
                {"source_label": "Gtr", "channel_number": 2},
            ],
            headers=auth_headers,
        )
        assert channels.status_code == 201, channels.text
        assert len(channels.json()) == 2
        assert all(r["kind"] == "channel" for r in channels.json())


async def test_venue_validate_returns_issues_for_invalid_edge(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        a = await client.post(
            f"{BASE}/venues/{venue_id}/graph/devices",
            json={"domain": "audio", "kind": "other", "name": "A", "expected_revision": 1},
            headers=auth_headers,
        )
        b = await client.post(
            f"{BASE}/venues/{venue_id}/graph/devices",
            json={"domain": "audio", "kind": "other", "name": "B", "expected_revision": 1},
            headers=auth_headers,
        )
        assert a.status_code == 201 and b.status_code == 201
        a_id, b_id = a.json()["id"], b.json()["id"]

        # An audio edge on ports the devices lack is invalid; force it through so it is stored.
        edge = await client.post(
            f"{BASE}/venues/{venue_id}/graph/edges",
            json={
                "signal": "audio",
                "src_device_id": a_id,
                "src_port": "out",
                "dst_device_id": b_id,
                "dst_port": "in",
            },
            params={"force": "true"},
            headers=auth_headers,
        )
        assert edge.status_code == 201, edge.text

        issues = await client.get(f"{BASE}/venues/{venue_id}/graph/validate", headers=auth_headers)
        assert issues.status_code == 200, issues.text
        codes = {i["code"] for i in issues.json()}
        assert "unknown_port" in codes


async def test_venue_power_load_returns_load(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        node = await client.post(
            f"{BASE}/venues/{venue_id}/graph/power-nodes",
            json={
                "name": "Main",
                "kind": "source",
                "rating_amps": 16,
                "outputs": [{"connector": "schuko", "count": 1, "phase": "L1"}],
            },
            headers=auth_headers,
        )
        assert node.status_code == 201, node.text

        load = await client.get(f"{BASE}/venues/{venue_id}/graph/power-load", headers=auth_headers)
        assert load.status_code == 200, load.text
        body = load.json()
        assert {"L1", "L2", "L3", "limit_w", "imbalance_pct"} <= set(body.keys())
        assert body["L1"] >= 0


async def test_venue_rigging_summary_returns_nodes(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        source = await client.post(
            f"{BASE}/venues/{venue_id}/graph/power-nodes",
            json={
                "name": "Mains",
                "kind": "source",
                "feed_connector": "cee63_3p",
                "rating_amps": 63,
                "outputs": [{"connector": "cee32_3p", "count": 2}],
            },
            headers=auth_headers,
        )
        assert source.status_code == 201, source.text

        node = await client.post(
            f"{BASE}/venues/{venue_id}/graph/power-nodes",
            json={
                "name": "Distro",
                "kind": "distro",
                "parent_id": source.json()["id"],
                "feed_connector": "cee32_3p",
                "outputs": [{"connector": "schuko", "count": 2}],
            },
            headers=auth_headers,
        )
        assert node.status_code == 201, node.text
        node_id = node.json()["id"]

        summary = await client.get(
            f"{BASE}/venues/{venue_id}/graph/rigging/summary", headers=auth_headers
        )
        assert summary.status_code == 200, summary.text
        nodes = summary.json()["nodes"]
        assert any(n["id"] == node_id for n in nodes)


async def test_venue_create_power_node(auth_headers):
    async with _client() as client:
        venue_id = await _make_venue(client, auth_headers)

        source = await client.post(
            f"{BASE}/venues/{venue_id}/graph/power-nodes",
            json={
                "name": "Mains",
                "kind": "source",
                "feed_connector": "cee63_3p",
                "rating_amps": 63,
                "outputs": [{"connector": "cee32_3p", "count": 2}],
            },
            headers=auth_headers,
        )
        assert source.status_code == 201, source.text

        node = await client.post(
            f"{BASE}/venues/{venue_id}/graph/power-nodes",
            json={
                "name": "FOH",
                "kind": "distro",
                "parent_id": source.json()["id"],
                "feed_connector": "cee32_3p",
                "outputs": [{"connector": "schuko", "count": 3}],
            },
            headers=auth_headers,
        )
        assert node.status_code == 201, node.text
        body = node.json()
        assert "id" in body and "attributes" in body
