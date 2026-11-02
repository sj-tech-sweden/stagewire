"""Rigging points on the graph: loads hold the point's public id, and deleting it clears them."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "/api/v1"


@pytest.mark.asyncio
async def test_a_rigging_point_is_a_node_and_deleting_it_unhangs_its_loads(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = auth_headers
        job_id = (await client.post(f"{BASE}/jobs", json={"title": "Truss"}, headers=h)).json()[
            "id"
        ]
        g = f"{BASE}/jobs/{job_id}/graph"
        point = (
            await client.post(
                f"{g}/rigging-points",
                json={"name": "FOH truss", "weight_capacity_kg": 100, "trim_height_cm": 600},
                headers=h,
            )
        ).json()
        assert point["kind"] == "rigging_point" and point["legacy_ref"] is None
        assert point["attributes"] == {"trim_height_cm": 600, "weight_capacity_kg": 100}

        # the legacy listing (and the weight summary) read the node
        listed = (await client.get(f"{BASE}/jobs/{job_id}/rigging-points", headers=h)).json()
        assert [(p["id"], p["name"]) for p in listed] == [(point["id"], "FOH truss")]

        fixture = await client.post(
            f"{g}/fixtures", json={"purpose": "Wash", "rigging_point_id": point["id"]}, headers=h
        )
        assert fixture.status_code == 201, fixture.text
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert summary["loads"][0]["rigging_point_id"] == point["id"]

        # an edit of the node is the point's edit
        res = await client.patch(
            f"{g}/devices/{point['id']}",
            json={
                "attributes": {"weight_capacity_kg": 50},
                "expected_revision": point["revision"],
            },
            headers=h,
        )
        assert res.status_code == 200, res.text
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert summary["points"][0]["weight_capacity_kg"] == 50

        node = res.json()
        assert (
            await client.delete(
                f"{g}/devices/{point['id']}",
                params={"expected_revision": node["revision"]},
                headers=h,
            )
        ).status_code == 204
        summary = (await client.get(f"{g}/rigging/summary", headers=h)).json()
        assert summary["points"] == []
        assert summary["loads"][0]["rigging_point_id"] is None
        fixtures = (await client.get(f"{BASE}/jobs/{job_id}/fixtures", headers=h)).json()
        assert fixtures[0]["rigging_point_id"] is None
