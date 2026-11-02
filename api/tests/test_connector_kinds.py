import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


@pytest.mark.asyncio
async def test_connector_kinds_are_shared_and_adding_an_existing_one_returns_it(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        res = await client.post(
            f"{BASE}/connector-kinds", json={"label": "Neutrik opticalCON"}, headers=h
        )
        assert res.status_code == 201, res.text
        assert res.json()["key"] == "neutrik-opticalcon"

        again = await client.post(
            f"{BASE}/connector-kinds", json={"label": "neutrik  OpticalCON "}, headers=h
        )
        assert again.status_code == 201 and again.json()["id"] == res.json()["id"]

        listed = (await client.get(f"{BASE}/connector-kinds", headers=h)).json()
        assert [k["key"] for k in listed].count("neutrik-opticalcon") == 1

        empty = await client.post(f"{BASE}/connector-kinds", json={"label": "***"}, headers=h)
        assert empty.status_code == 422

        gone = await client.delete(f"{BASE}/connector-kinds/{res.json()['id']}", headers=h)
        assert gone.status_code == 204
        missing = await client.delete(f"{BASE}/connector-kinds/{res.json()['id']}", headers=h)
        assert missing.status_code == 404
        assert "neutrik-opticalcon" not in [
            k["key"] for k in (await client.get(f"{BASE}/connector-kinds", headers=h)).json()
        ]


@pytest.mark.asyncio
async def test_connector_kinds_need_a_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(f"{BASE}/connector-kinds")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_a_custom_power_connector_is_known_to_the_power_tree_and_listed_in_its_catalog(
    auth_headers,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        needs_numbers = await client.post(
            f"{BASE}/connector-kinds", json={"label": "Hubbell 30 A", "power": True}, headers=h
        )
        assert needs_numbers.status_code == 422
        builtin = await client.post(
            f"{BASE}/connector-kinds",
            json={"label": "Schuko", "power": True, "amps": 16, "phases": 1},
            headers=h,
        )
        assert builtin.status_code == 409

        made = await client.post(
            f"{BASE}/connector-kinds",
            json={"label": "Hubbell 30 A", "power": True, "amps": 30, "phases": 1},
            headers=h,
        )
        assert made.status_code == 201, made.text
        catalog = (await client.get(f"{BASE}/power-connectors", headers=h)).json()
        hubbell = next(c for c in catalog if c["key"] == "hubbell-30-a")
        assert (hubbell["amps"], hubbell["phases"], hubbell["custom"]) == (30, 1, True)

        job_id = (await client.post(f"{BASE}/jobs", json={"title": "P"}, headers=h)).json()["id"]
        node = await client.post(
            f"{BASE}/jobs/{job_id}/power-nodes",
            json={"name": "Stage left", "kind": "source", "feed_connector": "hubbell-30-a"},
            headers=h,
        )
        assert node.status_code == 201, node.text

        assert (
            await client.delete(f"{BASE}/connector-kinds/{made.json()['id']}", headers=h)
        ).status_code == 204
        catalog = (await client.get(f"{BASE}/power-connectors", headers=h)).json()
        assert "hubbell-30-a" not in [c["key"] for c in catalog]
