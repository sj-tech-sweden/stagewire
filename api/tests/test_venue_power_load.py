"""Device-driven load for a venue's power supply.

The over-limit check must use the *actual* draw (device watts) rather than the sum of each
outlet's capacity (``rating_amps``), which would mark every multi-outlet panel as overloaded.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.venues.power_load import summarize_venue_power
from app.main import app

BASE = "/api/v1"


def _group(id, rating_amps, parent_id=None, is_incoming=False, kind=None):
    # kind drives the supply-root detection; is_incoming is kept as a legacy fallback for tests that
    # don't pass kind explicitly.
    if kind is None:
        kind = "incoming" if is_incoming else "group"
    return SimpleNamespace(
        id=id, rating_amps=rating_amps, parent_id=parent_id, is_incoming=is_incoming, kind=kind
    )


def _outlet(id, group_id, rating_amps=None):
    return SimpleNamespace(id=id, group_id=group_id, rating_amps=rating_amps)


@pytest.mark.asyncio
async def test_summarize_uses_device_watts_not_outlet_capacity():
    incoming = _group("in", 50.0, is_incoming=True)
    panel = _group("p", 32.0, parent_id="in")
    o1 = _outlet("o1", "p", 16.0)
    o2 = _outlet("o2", "p", 16.0)
    groups = [incoming, panel]
    outlets = [o1, o2]
    # 2 kW + 3 kW on the two sockets: each socket is within its own 16 A breaker, the panel (21.7 A)
    # is within 32 A, and the incoming (21.7 A) is within 50 A. No element is over.
    summary = summarize_venue_power(
        groups,
        outlets,
        outlet_watts={"o1": 2000.0, "o2": 3000.0},
        group_direct_watts={},
    )
    by_outlet = {e.id: e for e in summary.outlets}
    by_group = {e.id: e for e in summary.groups}
    assert by_outlet["o1"].over is False
    assert round(by_outlet["o1"].amps, 1) == 8.7
    assert by_group["p"].over is False
    assert round(by_group["p"].amps, 1) == 21.7
    supply = next(s for s in summary.supplies if s.id == "in")
    assert supply.over is False
    assert round(summary.total_amps, 1) == 21.7


@pytest.mark.asyncio
async def test_summarize_flags_over_limit_per_element():
    panel = _group("p", 10.0)
    outlet = _outlet("o", "p", 10.0)
    # 3 kW on a 10 A socket (13 A draw) is over, and the panel inherits the over (same draw).
    summary = summarize_venue_power(
        [panel], [outlet], outlet_watts={"o": 3000.0}, group_direct_watts={}
    )
    by_outlet = {e.id: e for e in summary.outlets}
    by_group = {e.id: e for e in summary.groups}
    assert by_outlet["o"].over is True
    assert by_group["p"].over is True


@pytest.mark.asyncio
async def test_summarize_aggregates_nested_groups_and_incoming():
    incoming = _group("in", 10.0, is_incoming=True)
    panel_a = _group("a", 10.0, parent_id="in")
    panel_b = _group("b", 32.0, parent_id="a")
    outlet = _outlet("o", "b", 16.0)
    summary = summarize_venue_power(
        [incoming, panel_a, panel_b],
        [outlet],
        outlet_watts={"o": 5000.0},
        group_direct_watts={},
    )
    by_group = {e.id: e for e in summary.groups}
    # The 5 kW draw sits on panel B's outlet; panel B is fine (21.7 A <= 32 A) but panel A and the
    # incoming carry the same total and are over their 10 A breakers.
    assert by_group["b"].over is False
    assert by_group["a"].over is True
    supply = next(s for s in summary.supplies if s.id == "in")
    assert supply.over is True


@pytest.mark.asyncio
async def test_summarize_ignores_stale_element_links():
    panel = _group("p", 16.0)
    # A device attributed to a deleted outlet must not inflate the surviving panel.
    summary = summarize_venue_power(
        [panel], [], outlet_watts={"gone": 9000.0}, group_direct_watts={}
    )
    assert summary.groups[0].watts == 0.0
    assert summary.total_watts == 0.0


async def _venue_with_supply(client, h, venue_id):
    # A representative supply tree: incoming mains -> a panel -> a fused circuit, with an outlet on
    # the circuit (outlets plug into circuits/groups, not directly into panels).
    incoming = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={"name": "Incoming", "rating_amps": 50, "kind": "incoming"},
            headers=h,
        )
    ).json()
    panel = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Panel A",
                "rating_amps": 32,
                "kind": "panel",
                "parent_id": incoming["id"],
            },
            headers=h,
        )
    ).json()
    circuit = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Circuit 1",
                "rating_amps": 16,
                "kind": "group",
                "parent_id": panel["id"],
            },
            headers=h,
        )
    ).json()
    outlet = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={
                "name": "O1",
                "connector": "schuko",
                "group_id": circuit["id"],
                "rating_amps": 16,
            },
            headers=h,
        )
    ).json()
    return incoming, panel, outlet


@pytest.mark.asyncio
async def test_venue_power_load_uses_base_rig_device_watts(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
        venue_id = venue["id"]
        incoming, panel, outlet = await _venue_with_supply(client, h, venue_id)

        # Seed the base rig with two devices plugged into the outlet (2 kW and 3 kW).
        device_a = str(uuid4())
        device_b = str(uuid4())
        res = await client.put(
            f"{BASE}/venues/{venue_id}/graph",
            json={
                "devices": [
                    {
                        "id": device_a,
                        "domain": "audio",
                        "kind": "other",
                        "name": "Amp",
                        "attributes": {"power_w": 2000, "venue_outlet_id": outlet["id"]},
                    },
                    {
                        "id": device_b,
                        "domain": "lighting",
                        "kind": "other",
                        "name": "LED",
                        "attributes": {"power_w": 3000, "venue_outlet_id": outlet["id"]},
                    },
                ],
                "edges": [],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text

        load = (await client.get(f"{BASE}/venues/{venue_id}/power-load", headers=h)).json()
        outlet_load = next(e for e in load["outlets"] if e["id"] == outlet["id"])
        panel_load = next(e for e in load["groups"] if e["id"] == panel["id"])
        incoming_load = next(s for s in load["supplies"] if s["id"] == incoming["id"])
        # 5 kW across the two devices: 21.7 A on the 16 A outlet (over), within the 32 A panel and
        # 50 A incoming (both fine).
        assert round(outlet_load["watts"]) == 5000
        assert outlet_load["over"] is True
        assert round(panel_load["amps"], 1) == 21.7
        assert panel_load["over"] is False
        assert incoming_load["over"] is False
        assert round(load["total_amps"], 1) == 21.7


@pytest.mark.asyncio
async def test_venue_power_load_flags_over_limit_from_devices(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
        venue_id = venue["id"]
        incoming, panel, outlet = await _venue_with_supply(client, h, venue_id)

        # 4 kW on the 16 A outlet (17.4 A) is over, and the panel/incoming inherit it.
        res = await client.put(
            f"{BASE}/venues/{venue_id}/graph",
            json={
                "devices": [
                    {
                        "id": str(uuid4()),
                        "domain": "audio",
                        "kind": "other",
                        "name": "Big amp",
                        "attributes": {"power_w": 4000, "venue_outlet_id": outlet["id"]},
                    }
                ],
                "edges": [],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text

        load = (await client.get(f"{BASE}/venues/{venue_id}/power-load", headers=h)).json()
        outlet_load = next(e for e in load["outlets"] if e["id"] == outlet["id"])
        # 4 kW on the 16 A outlet (17.4 A) is over; the 32 A panel and 50 A incoming absorb it.
        assert outlet_load["over"] is True
        assert next(e for e in load["groups"] if e["id"] == panel["id"])["over"] is False
        assert next(s for s in load["supplies"] if s["id"] == incoming["id"])["over"] is False


@pytest.mark.asyncio
async def test_job_power_load_attributes_device_watts_to_venue_outlet(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
        venue_id = venue["id"]
        incoming, panel, outlet = await _venue_with_supply(client, h, venue_id)
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Show"}, headers=h)).json()["id"]
        res = await client.put(
            f"{BASE}/jobs/{job_id}/venue", json={"venue_id": venue_id}, headers=h
        )
        assert res.status_code in (200, 201), res.text
        g = f"{BASE}/jobs/{job_id}/graph"

        # Plug the outlet into the job's power tree (creates a node carrying venue_outlet_id).
        source = (
            await client.post(f"{g}/venue-power/outlets/{outlet['id']}/source", headers=h)
        ).json()
        node_id = source["node"]["id"]

        gear = (
            await client.post(
                f"{g}/audio-devices",
                json={"name": "Amp", "device_type": "other", "power_watts": 2300},
                headers=h,
            )
        ).json()
        res = await client.put(
            f"{g}/loads/{gear['id']}",
            json={"power_node_id": node_id, "power_connector": "schuko"},
            headers=h,
        )
        assert res.status_code == 200, res.text

        load = (await client.get(f"{BASE}/jobs/{job_id}/power-load", headers=h)).json()
        # The outlet is in Panel A, so rigging serves it through the group's source node: the 2.3 kW
        # draw is attributed to the group (not the individual socket), and 10 A is within its 32 A.
        panel_load = next(e for e in load["groups"] if e["id"] == panel["id"])
        assert round(panel_load["watts"]) == 2300
        assert panel_load["over"] is False
        assert round(load["total_amps"], 2) == 10.0


@pytest.mark.asyncio
async def test_summarize_computes_each_supply_root_independently():
    # Mains and a generator are both roots; a device hung off the generator must not count against
    # the mains, and vice versa.
    incoming = _group("mains", 10.0, kind="incoming")
    gen = _group("gen", 10.0, kind="generator")
    mains_panel = _group("mp", 32.0, parent_id="mains")
    gen_panel = _group("gp", 32.0, parent_id="gen")
    mains_outlet = _outlet("mo", "mp", 16.0)
    gen_outlet = _outlet("go", "gp", 16.0)
    summary = summarize_venue_power(
        [incoming, gen, mains_panel, gen_panel],
        [mains_outlet, gen_outlet],
        outlet_watts={"mo": 5000.0, "go": 2000.0},
        group_direct_watts={},
    )
    by_supply = {s.id: s for s in summary.supplies}
    # 5 kW on the mains outlet trips its 10 A root; 2 kW on the generator is fine on its 10 A root.
    assert by_supply["mains"].over is True
    assert by_supply["gen"].over is False
    # The grand total is still both draws summed.
    assert round(summary.total_watts) == 7000


async def _venue_with_generator(client, h, venue_id):
    """A venue with a mains supply and a temporary generator, each feeding its own panel/circuit."""
    incoming = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={"name": "Mains", "rating_amps": 50, "kind": "incoming"},
            headers=h,
        )
    ).json()
    gen = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Gen 16A",
                "rating_amps": 16,
                "kind": "generator",
                "temporary": True,
            },
            headers=h,
        )
    ).json()
    mains_panel = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Panel A",
                "rating_amps": 32,
                "kind": "panel",
                "parent_id": incoming["id"],
            },
            headers=h,
        )
    ).json()
    # A breakout (temporary distro) hung off the generator, with a circuit + outlet.
    breakout = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Breakout",
                "rating_amps": 16,
                "kind": "breakout",
                "temporary": True,
                "parent_id": gen["id"],
            },
            headers=h,
        )
    ).json()
    circuit = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Gen Circuit",
                "rating_amps": 16,
                "kind": "group",
                "parent_id": breakout["id"],
            },
            headers=h,
        )
    ).json()
    outlet = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={
                "name": "GO1",
                "connector": "schuko",
                "group_id": circuit["id"],
                "rating_amps": 16,
            },
            headers=h,
        )
    ).json()
    return incoming, gen, mains_panel, breakout, circuit, outlet


@pytest.mark.asyncio
async def test_venue_generator_and_breakout_create_and_supply_listing(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Festival"}, headers=h)).json()
        venue_id = venue["id"]
        incoming, gen, mains_panel, breakout, circuit, outlet = await _venue_with_generator(
            client, h, venue_id
        )
        # The generator and breakout come back flagged temporary (kind + temporary in the response).
        assert gen["kind"] == "generator"
        assert gen["temporary"] is True
        assert breakout["kind"] == "breakout"
        assert breakout["temporary"] is True

        # Both supply roots are listed independently.
        load = (await client.get(f"{BASE}/venues/{venue_id}/power-load", headers=h)).json()
        by_supply = {s["id"]: s for s in load["supplies"]}
        assert incoming["id"] in by_supply
        assert gen["id"] in by_supply


@pytest.mark.asyncio
async def test_topology_rejects_invalid_parent_for_kind(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        venue = (await client.post(f"{BASE}/venues", json={"name": "Hall"}, headers=h)).json()
        venue_id = venue["id"]
        incoming = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-groups",
                json={"name": "Mains", "rating_amps": 50, "kind": "incoming"},
                headers=h,
            )
        ).json()
        panel = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-groups",
                json={
                    "name": "Panel",
                    "rating_amps": 32,
                    "kind": "panel",
                    "parent_id": incoming["id"],
                },
                headers=h,
            )
        ).json()

        # A generator (root) cannot have a parent.
        r = await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Bad Gen",
                "rating_amps": 16,
                "kind": "generator",
                "parent_id": incoming["id"],
            },
            headers=h,
        )
        assert r.status_code == 422, r.text

        # A circuit cannot sit directly under a generator (must be inside a board/breakout).
        r = await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Bad Circuit",
                "rating_amps": 16,
                "kind": "group",
                "parent_id": incoming["id"],
            },
            headers=h,
        )
        assert r.status_code == 422, r.text

        # A panel may hang off another panel (panel-to-panel feed) — valid.
        r = await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Sub Panel",
                "rating_amps": 32,
                "kind": "panel",
                "parent_id": panel["id"],
            },
            headers=h,
        )
        assert r.status_code == 201, r.text

        # But a panel cannot hang off a circuit (group).
        circuit = (
            await client.post(
                f"{BASE}/venues/{venue_id}/power-groups",
                json={
                    "name": "Circuit",
                    "rating_amps": 16,
                    "kind": "group",
                    "parent_id": panel["id"],
                },
                headers=h,
            )
        ).json()
        r = await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Bad Panel",
                "rating_amps": 32,
                "kind": "panel",
                "parent_id": circuit["id"],
            },
            headers=h,
        )
        assert r.status_code == 422, r.text

        # A breakout under the incoming supply is valid.
        r = await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={
                "name": "Breakout",
                "rating_amps": 16,
                "kind": "breakout",
                "parent_id": incoming["id"],
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
