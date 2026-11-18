from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


async def _job(client, h):
    return (await client.post(f"{BASE}/jobs", json={"title": "Devices"}, headers=h)).json()["id"]


@pytest.mark.asyncio
async def test_a_device_with_ports_and_specs_is_created_and_edited_through_the_graph(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        created = await client.post(
            f"{g}/audio-devices",
            json={
                "name": "Cam 1",
                "device_type": "camera",
                "sensor_width_mm": 9.6,
                "focal_min_mm": 4.3,
                "focal_max_mm": 86,
                "weight_kg": 2.5,
                "ports": [{"direction": "out", "connector": "SDI", "count": 2}],
            },
            headers=h,
        )
        assert created.status_code == 201, created.text
        node = created.json()
        assert node["domain"] == "video" and node["kind"] == "camera"
        assert node["attributes"]["sensor_width_mm"] == 9.6
        assert node["ports"][0]["id"] == "out-sdi" and node["ports"][0]["channels"] == 2

        # editing specs and ports in the graph writes the legacy row
        res = await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "name": "Cam 1 FOH",
                "kind": "ptz_camera",
                "attributes": {**node["attributes"], "focal_max_mm": 120, "max_distance_m": None},
                "ports": [
                    {"id": "out-sdi", "direction": "out", "connector": "SDI", "channels": 2},
                    {"id": "in-hdmi", "direction": "in", "connector": "HDMI", "channels": 1},
                    {"id": "out-video", "direction": "out", "signal": "video"},
                ],
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        legacy = (await client.get(f"{BASE}/jobs/{job_id}/devices", headers=h)).json()[0]
        assert (legacy["name"], legacy["device_type"], legacy["focal_max_mm"]) == (
            "Cam 1 FOH",
            "ptz_camera",
            120,
        )
        assert legacy["ports"] == [
            {"direction": "out", "connector": "SDI", "count": 2},
            {"direction": "in", "connector": "HDMI", "count": 1},
        ]
        refreshed = {d["name"]: d for d in (await client.get(g, headers=h)).json()["devices"]}
        assert {p["id"] for p in refreshed["Cam 1 FOH"]["ports"]} >= {"out-sdi", "in-hdmi"}


@pytest.mark.asyncio
async def test_effective_values_report_overrides_and_sources(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        mixer = (
            await client.post(
                f"{g}/audio-devices",
                json={"name": "Desk", "device_type": "mixer", "weight_kg": 12, "power_watts": 300},
                headers=h,
            )
        ).json()
        node = mixer
        await client.patch(
            f"{g}/devices/{node['id']}",
            json={
                "attributes": {**node["attributes"], "input_override": 48},
                "expected_revision": node["revision"],
            },
            headers=h,
        )
        values = (await client.get(f"{g}/effective", headers=h)).json()[node["id"]]
        assert values["input_count"] == 48 and values["input_source"] == "override"
        assert values["weight_kg_effective"] == 12 and values["weight_source"] == "manual"
        assert values["power_watts_effective"] == 300


@pytest.mark.asyncio
async def test_network_join_auto_inserts_switch_and_links(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        def dante(name, extra=None):
            ports = [
                {"id": "in-dante", "direction": "in", "signal": "data", "connector": "dante"},
                {
                    "id": "out-dante",
                    "direction": "out",
                    "signal": "data",
                    "connector": "dante",
                },
            ]
            if extra:
                ports.append(extra)
            return client.post(
                f"{g}/devices",
                json={
                    "name": name,
                    "domain": "audio",
                    "kind": "digital_stagebox",
                    "attributes": {"device_type": "digital_stagebox"},
                    "ports": ports,
                },
                headers=h,
            )

        a = (await dante("Stagebox A")).json()
        b = (await dante("Stagebox B")).json()

        res = await client.post(
            f"{g}/network-join",
            json={"a_device_id": a["id"], "b_device_id": b["id"], "name": "My Switch"},
            headers=h,
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["device"]["kind"] == "network"
        assert body["device"]["name"] == "My Switch"
        assert len(body["edges"]) == 2
        # One edge leaves A (out) and one arrives at B (in), both over data.
        assert {e["src_device_id"] for e in body["edges"]} == {a["id"], body["device"]["id"]}
        assert {e["dst_device_id"] for e in body["edges"]} == {b["id"], body["device"]["id"]}
        assert all(e["signal"] == "data" for e in body["edges"])

        graph = (await client.get(g, headers=h)).json()
        nets = [d for d in graph["devices"] if d["kind"] == "network"]
        assert len(nets) == 1
        assert len([e for e in graph["edges"] if e["signal"] == "data"]) == 2


@pytest.mark.asyncio
async def test_network_join_rejects_device_without_network_connector(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        xlr = (
            await client.post(
                f"{g}/devices",
                json={
                    "name": "Analog only",
                    "domain": "audio",
                    "kind": "analog_stagebox",
                    "attributes": {"device_type": "analog_stagebox"},
                    "ports": [{"id": "in-xlr", "direction": "in", "connector": "xlr3"}],
                },
                headers=h,
            )
        ).json()
        dante = (
            await client.post(
                f"{g}/devices",
                json={
                    "name": "Dante box",
                    "domain": "audio",
                    "kind": "digital_stagebox",
                    "attributes": {"device_type": "digital_stagebox"},
                    "ports": [
                        {
                            "id": "in-dante",
                            "direction": "in",
                            "signal": "data",
                            "connector": "dante",
                        },
                        {
                            "id": "out-dante",
                            "direction": "out",
                            "signal": "data",
                            "connector": "dante",
                        },
                    ],
                },
                headers=h,
            )
        ).json()
        res = await client.post(
            f"{g}/network-join",
            json={"a_device_id": xlr["id"], "b_device_id": dante["id"]},
            headers=h,
        )
        assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_network_join_tolerates_legacy_audio_signal_on_network_ports(auth_headers):
    # Devices whose Dante ports were stored with the legacy `audio` signal (pre-normalisation)
    # must still join: signal_mismatch is not a blocking issue for this endpoint.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        def legacy_dante(name):
            return client.post(
                f"{g}/devices",
                json={
                    "name": name,
                    "domain": "audio",
                    "kind": "digital_stagebox",
                    "attributes": {"device_type": "digital_stagebox"},
                    "ports": [
                        {
                            "id": "in-dante",
                            "direction": "in",
                            "signal": "audio",
                            "connector": "dante",
                        },
                        {
                            "id": "out-dante",
                            "direction": "out",
                            "signal": "audio",
                            "connector": "dante",
                        },
                    ],
                },
                headers=h,
            )

        a = (await legacy_dante("Legacy A")).json()
        b = (await legacy_dante("Legacy B")).json()
        res = await client.post(
            f"{g}/network-join",
            json={"a_device_id": a["id"], "b_device_id": b["id"]},
            headers=h,
        )
        assert res.status_code == 201, res.text
        assert len(res.json()["edges"]) == 2


@pytest.mark.asyncio
async def test_connect_stagebox_links_over_dante_and_makes_it_reachable(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        def dev(name, kind, ports):
            return client.post(
                f"{g}/devices",
                json={
                    "name": name,
                    "domain": "audio",
                    "kind": kind,
                    "attributes": {"device_type": kind},
                    "ports": ports,
                },
                headers=h,
            )

        mixer = (
            await dev(
                "GLD-80",
                "mixer",
                [{"id": "dsnake-in", "direction": "in", "signal": "data", "connector": "dsnake"}],
            )
        ).json()
        box = (
            await dev(
                "Stagebox",
                "digital_stagebox",
                [{"id": "dsnake-out", "direction": "out", "signal": "data", "connector": "dsnake"}],
            )
        ).json()

        res = await client.post(f"{g}/connect-stagebox", json={"stagebox_id": box["id"]}, headers=h)
        assert res.status_code == 201, res.text
        edge = res.json()["edge"]
        assert edge["signal"] == "data"
        assert edge["src_device_id"] == box["id"]
        assert edge["dst_device_id"] == mixer["id"]

        # The stagebox is now reachable from the mixer over the data edge (the §2 walk).
        from app.domains.audio import console

        edges = (await client.get(g, headers=h)).json()["edges"]
        edge_rows = [
            SimpleNamespace(
                signal=e["signal"],
                src_device_id=e["src_device_id"],
                dst_device_id=e["dst_device_id"],
            )
            for e in edges
        ]
        mixer_row = SimpleNamespace(
            id=mixer["id"], kind="mixer", name="GLD-80", attributes={}, ports=mixer["ports"]
        )
        box_row = SimpleNamespace(
            id=box["id"],
            kind="digital_stagebox",
            name="Stagebox",
            attributes={},
            ports=box["ports"],
        )
        reached = console.feedingStageboxes(mixer_row, [mixer_row, box_row], edge_rows)
        assert any(console.is_stagebox(d) for d in reached)


@pytest.mark.asyncio
async def test_connect_stagebox_prefers_matching_console_interface(auth_headers):
    # A console that carries BOTH dSnake and Dante network ports must link a dSnake stagebox to its
    # dSnake port, not the Dante one (otherwise the edge is dSnake->Dante and validate_edge rejects
    # it with "cannot mate"). The dSnake port is listed second to prove ordering does not win.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        def dev(name, kind, ports):
            return client.post(
                f"{g}/devices",
                json={
                    "name": name,
                    "domain": "audio",
                    "kind": kind,
                    "attributes": {"device_type": kind},
                    "ports": ports,
                },
                headers=h,
            )

        # The console must exist (and carry both interfaces) for the auto-pick to choose dSnake.
        await dev(
            "GLD-80",
            "mixer",
            [
                {"id": "dante-in", "direction": "in", "signal": "data", "connector": "dante"},
                {"id": "dsnake-in", "direction": "in", "signal": "data", "connector": "dsnake"},
            ],
        )
        box = (
            await dev(
                "Stagebox",
                "digital_stagebox",
                [{"id": "dsnake-out", "direction": "out", "signal": "data", "connector": "dsnake"}],
            )
        ).json()

        res = await client.post(f"{g}/connect-stagebox", json={"stagebox_id": box["id"]}, headers=h)
        assert res.status_code == 201, res.text
        edge = res.json()["edge"]
        assert edge["src_port"] == "dsnake-out"
        assert edge["dst_port"] == "dsnake-in"


@pytest.mark.asyncio
async def test_connect_stagebox_honours_explicit_ports(auth_headers):
    # The user can override the auto-pick and choose a specific stagebox output and console input
    # (e.g. the dSnake expander on both), and the link uses exactly those ports.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        def dev(name, kind, ports):
            return client.post(
                f"{g}/devices",
                json={
                    "name": name,
                    "domain": "audio",
                    "kind": kind,
                    "attributes": {"device_type": kind},
                    "ports": ports,
                },
                headers=h,
            )

        # The console must exist (with a base dSnake in and a dSnake-expander in) so the user can
        # explicitly choose the expander pair.
        await dev(
            "GLD-80",
            "mixer",
            [
                {"id": "dsnake-in", "direction": "in", "signal": "data", "connector": "dsnake"},
                {
                    "id": "dsnake-exp-in",
                    "direction": "in",
                    "signal": "data",
                    "connector": "dsnake",
                    "label": "dSnake Expander",
                },
            ],
        )
        box = (
            await dev(
                "Stagebox",
                "digital_stagebox",
                [
                    {
                        "id": "dsnake-out",
                        "direction": "out",
                        "signal": "data",
                        "connector": "dsnake",
                    },
                    {
                        "id": "dsnake-exp-out",
                        "direction": "out",
                        "signal": "data",
                        "connector": "dsnake",
                        "label": "dSnake Expander",
                    },
                ],
            )
        ).json()

        res = await client.post(
            f"{g}/connect-stagebox",
            json={
                "stagebox_id": box["id"],
                "stagebox_port": "dsnake-exp-out",
                "console_port": "dsnake-exp-in",
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
        edge = res.json()["edge"]
        assert edge["src_port"] == "dsnake-exp-out"
        assert edge["dst_port"] == "dsnake-exp-in"


@pytest.mark.asyncio
async def test_connect_stagebox_rejects_bad_explicit_port(auth_headers):
    # An explicit port that is not a real network port on the named device (or the wrong direction)
    # is rejected with a clear message rather than silently mis-linked.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"

        def dev(name, kind, ports):
            return client.post(
                f"{g}/devices",
                json={
                    "name": name,
                    "domain": "audio",
                    "kind": kind,
                    "attributes": {"device_type": kind},
                    "ports": ports,
                },
                headers=h,
            )

        # The console must exist with a network input so the bad-port rejection is about the port,
        # not the missing console.
        await dev(
            "GLD-80",
            "mixer",
            [{"id": "dsnake-in", "direction": "in", "signal": "data", "connector": "dsnake"}],
        )
        box = (
            await dev(
                "Stagebox",
                "digital_stagebox",
                [{"id": "dsnake-out", "direction": "out", "signal": "data", "connector": "dsnake"}],
            )
        ).json()

        res = await client.post(
            f"{g}/connect-stagebox",
            json={"stagebox_id": box["id"], "console_port": "does-not-exist"},
            headers=h,
        )
        assert res.status_code == 422, res.text
        assert "console_port" in res.text


@pytest.mark.asyncio
async def test_device_ports_accept_null_label(auth_headers):
    # Most ports are unnamed, so the frontend sends label=null. The Port schema must accept that
    # rather than rejecting the whole device with "Input should be a valid string" (label was a
    # non-optional str). Regression guard for the stagebox-with-XLR-ports save 422.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        res = await client.post(
            f"{g}/devices",
            json={
                "name": "Box",
                "domain": "audio",
                "kind": "digital_stagebox",
                "attributes": {"device_type": "digital_stagebox"},
                "ports": [
                    {
                        "id": "xlr-in",
                        "direction": "in",
                        "connector": "xlr3",
                        "channels": 8,
                        "label": None,
                    },
                    {
                        "id": "xlr-out",
                        "direction": "out",
                        "connector": "xlr3",
                        "channels": 8,
                        "label": None,
                    },
                ],
            },
            headers=h,
        )
        assert res.status_code == 201, res.text
        assert all(p["label"] is None for p in res.json()["ports"])


@pytest.mark.asyncio
async def test_connect_stagebox_rejects_non_stagebox(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = await _job(client, h)
        g = f"{BASE}/jobs/{job_id}/graph"
        mic = (
            await client.post(
                f"{g}/devices",
                json={
                    "name": "Mic",
                    "domain": "audio",
                    "kind": "other",
                    "attributes": {"device_type": "other"},
                    "ports": [],
                },
                headers=h,
            )
        ).json()
        res = await client.post(f"{g}/connect-stagebox", json={"stagebox_id": mic["id"]}, headers=h)
        assert res.status_code == 422, res.text


def test_validate_edge_accepts_bidirectional_both_port():
    # A 'both' transport port is an input AND an output, so it may sit at either end of an edge.
    from app.domains.graph import topology

    src = {
        "name": "Box",
        "id": "b",
        "ports": [{"id": "dsnake", "direction": "both", "connector": "dsnake", "signal": "data"}],
    }
    dst = {
        "name": "Mixer",
        "id": "m",
        "ports": [{"id": "dsnake", "direction": "both", "connector": "dsnake", "signal": "data"}],
    }
    issues = topology.validate_edge(
        {
            "signal": "data",
            "src_device_id": "b",
            "src_port": "dsnake",
            "dst_device_id": "m",
            "dst_port": "dsnake",
        },
        src,
        dst,
        [],
    )
    assert not any(i.code == "direction" for i in issues)
