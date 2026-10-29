from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import db as db_mod
from app.domains.audio.models import ProductionJob
from app.domains.graph import topology
from app.main import app

BASE = "/api/v1"


def port(pid, direction, **extra):
    return {"id": pid, "direction": direction, **extra}


def dev(did, name, ports, **extra):
    return {"id": did, "name": name, "ports": ports, "attributes": {}, **extra}


def edge(eid, src, sp, dst, dp, signal="audio", **extra):
    return {
        "id": eid,
        "signal": signal,
        "src_device_id": src,
        "src_port": sp,
        "dst_device_id": dst,
        "dst_port": dp,
        "channels": 1,
        **extra,
    }


def test_trace_walks_a_multi_tier_audio_chain_both_ways():
    edges = [
        edge("e1", "mic", "o", "box", "i1"),
        edge("e2", "box", "o", "stagebox", "i1"),
        edge("e3", "stagebox", "o", "foh", "i1"),
    ]
    down = topology.trace(edges, "mic", "downstream")
    assert [h.device_id for h in down.hops] == ["box", "stagebox", "foh"]
    assert [h.depth for h in down.hops] == [1, 2, 3]
    up = topology.trace(edges, "foh", "upstream")
    assert [h.device_id for h in up.hops] == ["stagebox", "box", "mic"]


def test_trace_is_signal_filtered_and_depth_capped():
    edges = [edge("e1", "a", "o", "b", "i"), edge("e2", "b", "o", "c", "i", signal="dmx")]
    assert [h.device_id for h in topology.trace(edges, "a", "downstream", signal="audio").hops] == [
        "b"
    ]
    capped = topology.trace(edges, "a", "downstream", max_depth=1)
    assert capped.truncated and len(capped.hops) == 1


def test_cycle_detection():
    edges = [edge("e1", "a", "o", "b", "i"), edge("e2", "b", "o", "c", "i")]
    assert topology.would_create_cycle(edges, "c", "a")
    assert topology.would_create_cycle(edges, "a", "a")
    assert not topology.would_create_cycle(edges, "a", "c")


def test_socapex_break_in_must_match_breakout_channel_count():
    break_in = dev(
        "s", "Soca In", [port("o", "out", signal="power", connector="socapex19", channels=6)]
    )
    breakout = dev(
        "b", "Breakout", [port("i", "in", signal="power", connector="socapex19", channels=6)]
    )
    good = edge("e", "s", "o", "b", "i", signal="power", channels=6)
    assert topology.validate_edge(good, break_in, breakout) == []

    narrow = dev(
        "b", "Breakout", [port("i", "in", signal="power", connector="socapex19", channels=3)]
    )
    codes = {i.code for i in topology.validate_edge(good, break_in, narrow)}
    assert "channel_count" in codes

    xlr = dev("b", "Breakout", [port("i", "in", signal="power", connector="xlr3", channels=6)])
    codes = {i.code for i in topology.validate_edge(good, break_in, xlr)}
    assert "connector_mismatch" in codes


def test_validate_flags_direction_signal_phase_and_port_reuse():
    a = dev("a", "A", [port("o", "out", signal="audio")])
    b = dev("b", "B", [port("i", "in", signal="video")])
    codes = {i.code for i in topology.validate_edge(edge("e", "a", "o", "b", "i"), a, b)}
    assert "signal_mismatch" in codes
    flipped = topology.validate_edge(edge("e", "b", "i", "a", "o"), b, a)
    assert {"direction"} <= {i.code for i in flipped}
    bad_phase = topology.validate_edge(edge("e", "a", "o", "b", "i", phase="L1"), a, b)
    assert "bad_phase" in {i.code for i in bad_phase}
    c = dev("c", "C", [port("i", "in", signal="audio")])
    d = dev("d", "D", [port("o", "out", signal="audio")])
    existing = [edge("x", "a", "o", "c", "i")]
    reuse = topology.validate_edge(edge("e", "d", "o", "c", "i"), d, c, existing)
    assert "port_in_use" in {i.code for i in reuse}


def test_phase_loads_sum_connected_power_draw():
    devices = {
        "p": dev("p", "Par", [], attributes={"power_w": 300}),
        "q": dev("q", "Moving", [], attributes={"power_w": 700}),
    }
    edges = [
        edge("e1", "d", "o", "p", "i", signal="power", phase="L1"),
        edge("e2", "d", "o", "q", "i", signal="power", phase="L2"),
    ]
    assert topology.phase_loads(devices, edges) == {"L1": 300.0, "L2": 700.0, "L3": 0.0}


async def _job(client, headers):
    res = await client.post(f"{BASE}/jobs", json={"title": "Graph Job"}, headers=headers)
    return res.json()["id"]


async def _device(client, headers, job_id, name, ports, domain="audio"):
    res = await client.post(
        f"{BASE}/jobs/{job_id}/graph/devices",
        json={"domain": domain, "name": name, "ports": ports},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_graph_api_build_chain_trace_and_conflicts(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _job(client, auth_headers)
        g = f"{BASE}/jobs/{job_id}/graph"
        mic = await _device(
            client,
            auth_headers,
            job_id,
            "SM58",
            [port("o", "out", signal="audio", connector="xlr3")],
        )
        box = await _device(
            client,
            auth_headers,
            job_id,
            "Floor box",
            [
                port("i", "in", signal="audio", connector="xlr3"),
                port("o", "out", signal="audio", connector="xlr3"),
            ],
        )
        foh = await _device(
            client,
            auth_headers,
            job_id,
            "FOH",
            [port("i1", "in", signal="audio", connector="xlr3")],
        )

        link = lambda s, sp, d, dp: client.post(  # noqa: E731
            f"{g}/edges",
            json={
                "signal": "audio",
                "src_device_id": s["id"],
                "src_port": sp,
                "dst_device_id": d["id"],
                "dst_port": dp,
            },
            headers=auth_headers,
        )
        assert (await link(mic, "o", box, "i")).status_code == 201
        assert (await link(box, "o", foh, "i1")).status_code == 201

        loop = await link(foh, "i1", mic, "o")
        assert loop.status_code == 422

        bad = await link(mic, "o", foh, "nope")
        assert bad.status_code == 422
        assert bad.json()["detail"]["code"] == "invalid_connection"

        trace = await client.get(
            f"{g}/devices/{mic['id']}/trace",
            params={"direction": "downstream"},
            headers=auth_headers,
        )
        assert [h["device_id"] for h in trace.json()["hops"]] == [box["id"], foh["id"]]
        assert (await client.get(f"{g}/validate", headers=auth_headers)).json() == []

        graph = await client.get(g, headers=auth_headers)
        assert len(graph.json()["devices"]) == 3 and len(graph.json()["edges"]) == 2

        moved = await client.patch(
            f"{g}/devices/{box['id']}",
            json={"canvas_x_cm": 120, "canvas_y_cm": 80, "expected_revision": 1},
            headers=auth_headers,
        )
        assert moved.status_code == 200 and moved.json()["revision"] == 2
        stale = await client.patch(
            f"{g}/devices/{box['id']}",
            json={"name": "Other", "expected_revision": 1},
            headers=auth_headers,
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current"]["canvas_x_cm"] == 120

        stale_delete = await client.delete(
            f"{g}/devices/{box['id']}", params={"expected_revision": 1}, headers=auth_headers
        )
        assert stale_delete.status_code == 409
        removed = await client.delete(
            f"{g}/devices/{box['id']}", params={"expected_revision": 2}, headers=auth_headers
        )
        assert removed.status_code == 204
        assert (await client.get(g, headers=auth_headers)).json()["edges"] == []


@pytest.mark.asyncio
async def test_batch_create_and_power_load(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_id = await _job(client, auth_headers)
        g = f"{BASE}/jobs/{job_id}/graph"
        res = await client.post(
            f"{g}/devices/batch",
            json=[
                {
                    "domain": "power",
                    "name": "Distro",
                    "ports": [port("o1", "out", signal="power", max_connections=2)],
                },
                {
                    "domain": "lighting",
                    "name": "Par",
                    "attributes": {"power_w": 400},
                    "ports": [port("p", "in", signal="power")],
                },
            ],
            headers=auth_headers,
        )
        assert res.status_code == 201 and len(res.json()) == 2
        distro, par = res.json()
        edge_res = await client.post(
            f"{g}/edges",
            json={
                "signal": "power",
                "src_device_id": distro["id"],
                "src_port": "o1",
                "dst_device_id": par["id"],
                "dst_port": "p",
                "phase": "L2",
            },
            headers=auth_headers,
        )
        assert edge_res.status_code == 201, edge_res.text
        load = await client.get(f"{g}/power-load", headers=auth_headers)
        assert load.json()["L2"] == 400 and load.json()["imbalance_pct"] == 100.0


class FakeStockwire:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    async def add_requirement(self, job_id, body):
        if self.fail:
            raise RuntimeError("nope")
        self.calls.append((job_id, body))
        return {"id": 1}


@pytest.mark.asyncio
async def test_request_stockwire_booking_flags_unbooked_item(auth_headers):
    from app.domains.graph.router import get_stockwire_client

    fake = FakeStockwire()
    app.dependency_overrides[get_stockwire_client] = lambda: fake
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            job_id = await _job(client, auth_headers)
            g = f"{BASE}/jobs/{job_id}/graph"
            created = await client.post(
                f"{g}/devices",
                json={
                    "domain": "audio",
                    "name": "Wireless rx",
                    "stockwire_product_id": "42",
                    "stockwire_booked": False,
                },
                headers=auth_headers,
            )
            did = created.json()["id"]
            url = f"{g}/devices/{did}/request-stockwire"

            unlinked = await client.post(url, headers=auth_headers)
            assert unlinked.status_code == 409

            async with db_mod.SessionLocal() as db:
                job = await db.get(ProductionJob, UUID(job_id))
                job.stockwire_job_id = "77"
                await db.commit()

            ok = await client.post(url, headers=auth_headers)
            assert ok.status_code == 200, ok.text
            assert ok.json()["stockwire_booked"] is True
            assert ok.json()["stockwire_request_status"] == "requested"
            assert fake.calls[0][0] == "77" and fake.calls[0][1]["product_id"] == "42"

            fake.fail = True
            other = await client.post(
                f"{g}/devices",
                json={"domain": "audio", "name": "Mic", "stockwire_product_id": "9"},
                headers=auth_headers,
            )
            failed = await client.post(
                f"{g}/devices/{other.json()['id']}/request-stockwire", headers=auth_headers
            )
            assert failed.status_code == 502
            listed = await client.get(g, headers=auth_headers)
            statuses = {d["name"]: d["stockwire_request_status"] for d in listed.json()["devices"]}
            assert statuses["Mic"] == "failed"
    finally:
        app.dependency_overrides.pop(get_stockwire_client, None)


@pytest.mark.asyncio
async def test_catalog_search_degrades_to_empty_when_unconfigured(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            f"{BASE}/stockwire/catalog/search",
            params={"q": "sm58", "category": ["Audio"], "attr": "connector:xlr3"},
            headers=auth_headers,
        )
        assert res.status_code == 200 and res.json()["items"] == []
        kids = await client.get(f"{BASE}/stockwire/catalog/cases/5/children", headers=auth_headers)
        assert kids.json() == {"items": []}
