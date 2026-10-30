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
