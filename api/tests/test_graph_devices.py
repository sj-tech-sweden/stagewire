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
