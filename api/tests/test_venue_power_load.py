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


def _group(id, rating_amps, parent_id=None, is_incoming=False):
    return SimpleNamespace(
        id=id, rating_amps=rating_amps, parent_id=parent_id, is_incoming=is_incoming
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
    assert summary.incoming.over is False
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
    assert summary.incoming.over is True


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
            json={"name": "Panel A", "rating_amps": 32, "kind": "panel", "parent_id": incoming["id"]},
            headers=h,
        )
    ).json()
    circuit = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-groups",
            json={"name": "Circuit 1", "rating_amps": 16, "kind": "group", "parent_id": panel["id"]},
            headers=h,
        )
    ).json()
    outlet = (
        await client.post(
            f"{BASE}/venues/{venue_id}/power-outlets",
            json={"name": "O1", "connector": "schuko", "group_id": circuit["id"], "rating_amps": 16},
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
        incoming_load = load["incoming"]
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
        assert load["incoming"]["over"] is False


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
        # draw is attributed to the group (not the individual socket), and 10 A is within its 32 A.
        panel_load = next(e for e in load["groups"] if e["id"] == panel["id"])
        assert round(panel_load["watts"]) == 2300
        assert panel_load["over"] is False
        assert round(load["total_amps"], 2) == 10.0
